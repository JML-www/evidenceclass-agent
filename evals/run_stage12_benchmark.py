"""Offline performance baseline for stage 12.

The baseline is deliberately *deterministic and honest*: it measures the work that
can actually run in an offline CI environment (payload hashing and upload, the
deterministic agent graph, and the five artifact renderers) and records the
model/media-dependent stages as ``null`` with an explicit skip reason.  No real
provider latency, token count or cost is ever claimed without authorization.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from packages.agent_runtime import AgentGraph, AgentState, CapabilitySnapshot, RetryBudget
from packages.evidence_engine import EvidenceEngineService
from packages.evidence_engine.renderers import (
    render_actions_csv as render_actions_csv_artifact,
)
from packages.evidence_engine.renderers import (
    render_evidence_csv as render_evidence_csv_artifact,
)
from packages.evidence_engine.renderers import render_html as render_html_artifact
from packages.evidence_engine.renderers import render_json as render_json_artifact
from packages.evidence_engine.renderers import render_markdown as render_markdown_artifact
from packages.object_storage import InMemoryObjectStore
from packages.observability import STAGE_NAMES, StageTimeline
from packages.observability import metrics as metrics_registry
from packages.observability.timing import peak_memory_mb

ROOT = Path(__file__).resolve().parents[1]

BENCHMARK_VERSION = "0.12.0"
DEFAULT_REPEATS = 5

#: Stages that require a real VLM/ASR/OCR/retrieval provider and are therefore
#: reported as unknown rather than fabricated.
SKIPPED_STAGES: tuple[str, ...] = (
    "probe_ms",
    "frame_extract_ms",
    "asr_ms",
    "ocr_ms",
    "vlm_ms",
    "retrieval_ms",
)
MEASURED_STAGES: tuple[str, ...] = (
    "upload_ms",
    "agent_overhead_ms",
    "artifact_ms",
    "end_to_end_ms",
)


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    repeat: int
    payload: Callable[[], dict[str, Any]]
    notes: str


def _frame(index: int, minutes: float, students: int) -> dict[str, Any]:
    focused = max(0, students - 4 - (index % 3))
    return {
        "frame_id": f"bench_{index:03d}",
        "time": f"{int(minutes):02d}:{int((minutes % 1) * 60):02d}",
        "estimated_total_students": students,
        "student_behaviors": {
            "focused": focused,
            "head_down_reading_or_writing": 2,
            "hand_raised": index % 5,
            "discussion": index % 2,
            "phone_use": 0,
            "sleeping_or_desk_down": 0,
            "left_seat": 0,
            "distracted": students - focused - 2,
        },
        "teacher_behaviors": {
            "teaching": index % 2 == 0,
            "patrolling": index % 3 == 0,
            "guiding_students": index % 4 == 0,
        },
        "classroom_stage": ["introduction", "instruction", "interaction", "practice", "summary"][
            index % 5
        ],
        "evidence": [f"Synthetic benchmark observation {index}."],
        "confidence": 0.9,
    }


def _video_payload(
    duration_seconds: int, *, cameras: int = 1, students: int = 40
) -> dict[str, Any]:
    minutes = max(1, duration_seconds // 60)
    frame_count = max(2, minutes)
    frames = [
        _frame(index + 1, (index + 1) * (minutes / frame_count), students)
        for index in range(frame_count)
    ]
    return {
        "analysisMode": "video",
        "courseInfo": {
            "courseName": f"Synthetic benchmark lesson ({minutes} min)",
            "className": "Synthetic benchmark class",
            "chapter": "Performance baseline",
            "lessonTime": "synthetic",
            "studentCount": students,
        },
        "observationGoal": "Measure the deterministic pipeline; do not claim model accuracy.",
        "sourceFiles": [
            {"name": f"camera-{camera + 1}.mp4", "type": "synthetic_video",
             "durationSeconds": duration_seconds}
            for camera in range(cameras)
        ],
        "frames": frames,
        "regionHeatmap": {
            "front": {"visibility": "visible", "focus": 90, "interaction": 80},
            "middle": {"visibility": "visible", "focus": 85, "interaction": 75},
            "back": {"visibility": "visible", "focus": 80, "interaction": 60},
        },
        "teacherBehaviorDurations": {
            "teaching": minutes * 30,
            "patrolling": minutes * 15,
            "guiding": minutes * 12,
            "blackboardWriting": minutes * 10,
            "questioning": minutes * 12,
            "usingSlides": minutes * 14,
        },
        "teacherPositionDurations": {
            "podium": minutes * 40,
            "front_zone": minutes * 10,
            "middle_zone": minutes * 8,
            "back_zone": minutes * 5,
        },
    }


def _image_payload() -> dict[str, Any]:
    return {
        "analysisMode": "image",
        "courseInfo": {
            "courseName": "Synthetic benchmark image",
            "className": "Synthetic benchmark class",
            "chapter": "Performance baseline",
            "lessonTime": "current image",
            "studentCount": 24,
        },
        "observationGoal": "Measure a single 1080p-equivalent observation unit.",
        "sourceFiles": [{"name": "image-sample-001.jpg", "type": "image"}],
        "frames": [
            {
                "frame_id": "image_001",
                "time": "current image",
                "visible_student_count": 18,
                "student_behaviors": {
                    "focused": 15,
                    "head_down_reading_or_writing": 5,
                    "hand_raised": 2,
                    "discussion": 0,
                    "distracted": 1,
                },
                "teacher_behaviors": {
                    "teaching": True,
                    "patrolling": False,
                    "guiding_students": True,
                },
                "classroom_stage": "instruction",
                "evidence": ["Synthetic benchmark image observation."],
                "confidence": 0.9,
            }
        ],
        "regionHeatmap": {
            "front": {"visibility": "visible", "focus": 92, "interaction": 85},
            "middle": {"visibility": "visible", "focus": 88, "interaction": 78},
            "back": {"visibility": "visible", "focus": 83, "interaction": 62},
        },
        # Image mode must not carry temporal duration summaries or temporal
        # teacher events; the engine rejects that input by contract.
    }


def scenarios(repeats: int) -> list[Scenario]:
    return [
        Scenario(
            key="image-1080p",
            label="Single 1080p observation unit",
            repeat=repeats,
            payload=_image_payload,
            notes="One frame; structured observation JSON only.",
        ),
        Scenario(
            key="video-2min",
            label="2-minute 720p recording",
            repeat=repeats,
            payload=lambda: _video_payload(120),
            notes="Single camera, two sampled frames.",
        ),
        Scenario(
            key="video-10min",
            label="10-minute 720p recording",
            repeat=repeats,
            payload=lambda: _video_payload(600),
            notes="Single camera, ten sampled frames.",
        ),
        Scenario(
            key="video-46min-dual",
            label="46-minute dual-camera recording (pressure item)",
            repeat=repeats,
            payload=lambda: _video_payload(2_765, cameras=2),
            notes="Two cameras; the stress item that drives queue admission control.",
        ),
    ]


def _initial_state() -> AgentState:
    return AgentState(
        run_id=uuid4(),
        job_id=uuid4(),
        user_goal="benchmark the deterministic classroom evidence pipeline",
        mode="video",
        capabilities=CapabilitySnapshot(
            available_tools=["inspect_media", "observe_media", "verify_claims"]
        ),
        retry_budget=RetryBudget(remaining_tool_retries=2, remaining_model_retries=1),
    )


def _one_iteration(scenario: Scenario) -> dict[str, float | None]:
    timeline = StageTimeline()
    payload = scenario.payload()
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")

    store = InMemoryObjectStore()
    key = f"benchmark/{scenario.key}/{uuid4()}.json"

    def upload() -> None:
        sha256(raw).hexdigest()
        store.put(key, raw, "application/json")

    timeline.measure("upload_ms", upload)

    service = EvidenceEngineService()

    def run_agent() -> dict[str, Any]:
        context: dict[str, Any] = {"has_audio": False}
        AgentGraph().run(_initial_state(), context=context)
        return service.analyze_payload(payload)

    result = timeline.measure("agent_overhead_ms", run_agent)

    def render() -> None:
        render_html_artifact(result)
        render_markdown_artifact(result)
        render_evidence_csv_artifact(result)
        render_actions_csv_artifact(result)
        render_json_artifact(result)

    timeline.measure("artifact_ms", render)

    stages = timeline.finalize()
    stages["peak_memory_mb"] = peak_memory_mb()
    stages["upload_bytes"] = float(len(raw))
    for name in SKIPPED_STAGES:
        stages.setdefault(name, None)
    return stages


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 3)


def run_benchmark(*, repeats: int = DEFAULT_REPEATS) -> dict[str, Any]:
    tracemalloc.start()
    results: list[dict[str, Any]] = []
    for scenario in scenarios(repeats):
        samples: list[dict[str, float | None]] = []
        for _ in range(scenario.repeat):
            samples.append(_one_iteration(scenario))
        aggregates: dict[str, dict[str, float | None]] = {}
        for stage in (*STAGE_NAMES, "peak_memory_mb", "upload_bytes"):
            values = [
                float(sample[stage])
                for sample in samples
                if sample.get(stage) is not None
            ]
            if not values:
                aggregates[stage] = {"p50": None, "p95": None, "min": None, "max": None}
                continue
            aggregates[stage] = {
                "p50": round(statistics.median(values), 3),
                "p95": _percentile(values, 0.95),
                "min": round(min(values), 3),
                "max": round(max(values), 3),
            }
        registry = metrics_registry()
        for stage in MEASURED_STAGES:
            value = aggregates[stage]["p50"]
            if value is not None:
                registry.observe(
                    f"evidenceclass_benchmark_{stage.removesuffix('_ms')}_milliseconds",
                    value,
                    labels={"scenario": scenario.key},
                    help="Offline benchmark median per scenario",
                )
        results.append(
            {
                "scenario": scenario.key,
                "label": scenario.label,
                "notes": scenario.notes,
                "repeats": scenario.repeat,
                "stages": aggregates,
            }
        )
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or "unknown",
            "cpu_count": _cpu_count(),
        },
        "models": {
            "mode": "deterministic offline adapters only",
            "provider_calls": 0,
            "note": "Real VLM/ASR/OCR/LLM tracks are skipped without explicit authorization.",
        },
        "samples": {"repeats_per_scenario": repeats, "scenario_count": len(results)},
        "limitations": [
            "Model-dependent stages are reported as null; never as measured accuracy or latency.",
            "Inputs are synthetic structured observations, not real classroom recordings.",
            "Wall-clock values include Python interpreter noise on a shared workstation.",
            "Token counts and cost are zero because no paid provider is invoked.",
            "tracemalloc peak is an in-process allocation high-water mark, not process RSS.",
        ],
        "results": results,
        "metrics_snapshot": registry.snapshot(),
        "tracemalloc_peak_mb": round(peak / (1024 * 1024), 3),
    }


def _cpu_count() -> int:
    import os

    return os.cpu_count() or 1


def render_markdown(report: dict[str, Any]) -> str:
    env = report["environment"]
    lines = [
        f"# Performance baseline — EvidenceClass Agent v{report['benchmark_version']}",
        "",
        f"Generated `{report['generated_at']}` by `evals/run_stage12_benchmark.py`.",
        "",
        "## Environment",
        "",
        f"- Python: `{env['python']}` on `{env['platform']}`",
        f"- Machine: `{env['machine']}` / `{env['processor']}` · CPU count: {env['cpu_count']}",
        f"- Models: {report['models']['mode']} (provider calls: "
        f"{report['models']['provider_calls']})",
        f"- Repeats per scenario: {report['samples']['repeats_per_scenario']}",
        "",
        "## Results (median / p95, milliseconds unless stated)",
        "",
        "| Scenario | Stage | p50 | p95 | min | max |",
        "|----------|-------|-----|-----|-----|-----|",
    ]
    for item in report["results"]:
        for stage in (*MEASURED_STAGES, *SKIPPED_STAGES, "peak_memory_mb", "upload_bytes"):
            stats = item["stages"][stage]
            unit = "MB" if stage == "peak_memory_mb" else ("B" if stage == "upload_bytes" else "ms")
            p50 = "n/a" if stats["p50"] is None else f"{stats['p50']} {unit}"
            p95 = "n/a" if stats["p95"] is None else f"{stats['p95']} {unit}"
            low = "n/a" if stats["min"] is None else f"{stats['min']}"
            high = "n/a" if stats["max"] is None else f"{stats['max']}"
            lines.append(
                f"| `{item['scenario']}` | `{stage}` | {p50} | {p95} | {low} | {high} |"
            )
    lines.extend(["", "## Skipped stages and why", ""])
    for stage in SKIPPED_STAGES:
        lines.append(
            f"- `{stage}` — needs a real media/model provider; reported as unknown, "
            "not estimated."
        )
    lines.extend(["", "## Limitations", ""])
    for note in report["limitations"]:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the stage-12 offline benchmark.")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "evals" / "reports"),
        help="Directory for the Markdown and JSON reports",
    )
    args = parser.parse_args(argv)
    report = run_benchmark(repeats=max(1, args.repeats))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stem = f"benchmark-v{report['benchmark_version']}"
    (output / f"{stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (output / f"{stem}.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"report": str(output / f"{stem}.md"), "results": len(report["results"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
