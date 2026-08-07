"""Build one deterministic semantic result consumed by every renderer."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from packages.contracts import AnalysisResult, RegionObservation

from .actions import build_actions
from .artifacts import anonymize
from .evidence import build_evidence, time_to_seconds
from .metrics import (
    aggregate_metric,
    comparable_region_values,
    evaluate_rubric,
    frame_metrics,
    percentage_distribution,
)
from .validation import mode_capabilities, validate_payload

ENGINE_SCHEMA_VERSION = "engine.v0.1"
SUMMARY_METRICS = ("focus", "participation", "interaction", "teacherGuidance", "abnormalRate")


def _canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _duration_seconds(payload: dict[str, Any]) -> float | None:
    if payload["analysisMode"] == "image":
        return None
    durations = [
        source.get("durationSeconds")
        for source in payload.get("sourceFiles", [])
        if source.get("durationSeconds") is not None
    ]
    return float(max(durations)) if durations else None


def _region_views(payload: dict[str, Any]) -> list[dict[str, Any]]:
    views = []
    for region_id, raw_region in payload.get("regionHeatmap", {}).items():
        views.append(
            {
                "region_id": region_id,
                "visibility": raw_region["visibility"],
                "metrics": {
                    "focus": (
                        float(raw_region["focus"]) if raw_region.get("focus") is not None else None
                    ),
                    "interaction": (
                        float(raw_region["interaction"])
                        if raw_region.get("interaction") is not None
                        else None
                    ),
                },
            }
        )
    return views


def _region_comparisons(regions: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    comparisons: dict[str, dict[str, Any] | None] = {}
    for metric_key in ("focus", "interaction"):
        values = comparable_region_values(regions, metric_key)
        if len(values) < 2:
            comparisons[metric_key] = None
            continue
        minimum = min(values, key=lambda item: (item[1], item[0]))
        maximum = max(values, key=lambda item: (item[1], item[0]))
        comparisons[metric_key] = {
            "minimumRegion": minimum[0],
            "maximumRegion": maximum[0],
            "gap": round(maximum[1] - minimum[1], 1),
        }
    return comparisons


def build_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and transform a structured observation without performing I/O."""
    validate_payload(payload)
    input_sha256 = _canonical_sha256(payload)
    task_id = str(payload.get("taskId") or f"task-{input_sha256[:12]}")
    mode = payload["analysisMode"]
    fallback_total = int(payload.get("courseInfo", {}).get("studentCount") or 0)

    evidence = build_evidence(payload)
    evidence_ids_by_source: dict[str, list[str]] = {}
    for item in evidence:
        evidence_ids_by_source.setdefault(item.source_ref, []).append(item.evidence_id)

    metric_frames = []
    rendered_frames = []
    for frame_index, frame in enumerate(payload["frames"]):
        source_ref = str(frame.get("frame_id") or f"frame-{frame_index + 1}")
        metrics = frame_metrics(frame, fallback_total=fallback_total, mode=mode)
        duration = float(frame.get("observationDurationSeconds") or 1.0)
        metric_frames.append({"metrics": metrics, "observationDurationSeconds": duration})
        rendered_frames.append(
            {
                "sourceRef": source_ref,
                "timestampSec": time_to_seconds(frame.get("time")),
                "observationDurationSec": duration,
                "classroomStage": frame.get("classroom_stage"),
                "metrics": metrics,
                "evidenceIds": evidence_ids_by_source.get(source_ref, []),
            }
        )

    summary_metrics = {
        key: aggregate_metric(metric_frames, key) for key in SUMMARY_METRICS
    }
    rubric_result = None
    if payload.get("rubric") is not None:
        rubric_result = evaluate_rubric(summary_metrics, payload["rubric"])

    regions = _region_views(payload)
    region_contracts = [
        RegionObservation(region_id=region["region_id"], visibility=region["visibility"])
        for region in regions
    ]
    lesson_duration = _duration_seconds(payload)
    contract_result = AnalysisResult(
        task_id=task_id,
        analysis_mode=mode,
        region_observations=region_contracts,
        evidence=evidence,
        lesson_duration_sec=lesson_duration,
        observed_duration_sec=lesson_duration,
    )
    evidence_ids = [item.evidence_id for item in evidence]

    return {
        "schemaVersion": ENGINE_SCHEMA_VERSION,
        "contractVersion": contract_result.schema_version,
        "taskId": task_id,
        "analysisMode": mode,
        "inputSha256": input_sha256,
        "courseInfo": anonymize(payload.get("courseInfo", {})),
        "capabilities": mode_capabilities(payload),
        "summary": {
            "metrics": summary_metrics,
            "overall": rubric_result["overall"] if rubric_result else None,
            "rubricSource": rubric_result["source"] if rubric_result else None,
            "normalizedWeights": rubric_result["normalizedWeights"] if rubric_result else {},
        },
        "frames": rendered_frames,
        "regions": regions,
        "regionComparisons": _region_comparisons(regions),
        "distributions": {
            "teacherBehavior": percentage_distribution(
                payload.get("teacherBehaviorDurations", {})
            ),
            "teacherPosition": percentage_distribution(
                payload.get("teacherPositionDurations", {})
            ),
        },
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "actions": build_actions(summary_metrics, evidence_ids),
        "contractResult": contract_result.model_dump(mode="json"),
        "methodology": {
            "measurementType": "descriptive",
            "accuracyClaimed": False,
            "unknownValuePolicy": "null-not-zero",
        },
    }
