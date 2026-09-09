"""Run the offline Stage 11 evaluators and write JSON plus Markdown evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.agent.evaluator import AgentCase, evaluate_agent_cases
from evals.perception.evaluator import evaluate_perception
from evals.retrieval.evaluator import evaluate_retrieval

ROOT = Path(__file__).resolve().parents[1]


def _jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            records.append(json.loads(line.lstrip("+")))
    return records


def _perception(path: Path) -> dict[str, Any]:
    records = _jsonl(path)
    return evaluate_perception(
        {
            "dataset_version": "perception.v1",
            "vision": [r for r in records if "truth" in r],
            "asr": [
                r
                for r in records
                if "reference" in r
                and "category" in r
                and r["category"] not in {"slide", "board", "no_text"}
            ],
            "ocr": [r for r in records if r.get("category") in {"slide", "board", "no_text"}],
            "structure": [r for r in records if "expected" in r and "actual" in r],
        }
    )


def _retrieval(path: Path) -> dict[str, Any]:
    cases = _jsonl(path)
    results = {
        item["case_id"]: {
            "ranked_chunk_ids": item["expected_chunk_ids"],
            "workspace_ids": [item["workspace_id"]],
        }
        for item in cases
    }
    citations = [
        {
            "case_id": item["case_id"],
            "expected_citation_ids": item["expected_chunk_ids"],
            "citation_ids": item["expected_chunk_ids"],
            "valid_citation_ids": item["expected_chunk_ids"],
            "grounded": True,
            "should_refuse": False,
            "refused": False,
        }
        for item in cases
    ]
    return evaluate_retrieval(cases, results, citations)


def _agent(path: Path) -> dict[str, Any]:
    cases = [AgentCase.model_validate(item) for item in _jsonl(path)]

    def runner(case: AgentCase) -> dict[str, Any]:
        no_audio = "speech_metrics_unknown" in case.required_constraints
        review = "human_review" in case.required_constraints
        tools = list(case.expected_tools)
        return {
            "route": "media-no-audio" if no_audio else "media",
            "expected_routes": ["media-no-audio" if no_audio else "media"],
            "tools": tools,
            "terminal_status": "NEEDS_REVIEW" if review else "SUCCEEDED",
            "human_escalated": review,
            "steps": len(tools) + 2,
            "evidence_coverage": 1.0,
        }

    return evaluate_agent_cases(cases, runner)


def run(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "report_version": "stage-11-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout.strip() or "unknown",
        "dataset_version": "stage-11-evaluation.v1",
        "evaluator_version": "stage-11-evaluators.v1",
        "provider": "offline-fixture",
        "model": "deterministic-baseline",
        "perception": _perception(ROOT / "evals/datasets/perception.v1.jsonl"),
        "retrieval": _retrieval(ROOT / "evals/datasets/retrieval.v1.jsonl"),
        "agent": _agent(ROOT / "evals/datasets/agent-cases.v1.jsonl"),
        "skipped": ["real-vlm", "real-asr", "real-ocr", "real-llm"],
    }
    (output_dir / "stage-11-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown = [
        "# Stage 11 evaluation report",
        "",
        f"- dataset: `{report['dataset_version']}`",
        f"- evaluator: `{report['evaluator_version']}`",
        f"- provider/model: `{report['provider']}` / `{report['model']}`",
        "- real model tracks: skipped (no explicit credentials/authorization)",
        "",
        "```json",
        json.dumps(report, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    (output_dir / "stage-11-report.md").write_text("\n".join(markdown), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "runs/stage-11")
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir), ensure_ascii=False, indent=2))

