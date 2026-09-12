from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.agent.evaluator import AgentCase, evaluate_agent_cases
from evals.perception.evaluator import evaluate_perception
from evals.retrieval.evaluator import evaluate_retrieval

ROOT = Path(__file__).resolve().parents[3]


def _jsonl(name: str) -> list[dict]:
    path = ROOT / "evals" / "datasets" / name
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def test_perception_fixture_counts_and_unknown_boundary() -> None:
    records = _jsonl("perception.v1.jsonl")
    report = evaluate_perception(
        {
            "vision": [item for item in records if "truth" in item],
            "asr": [
                item
                for item in records
                if item.get("category") in {"clean", "noise", "proper_noun", "overlap"}
            ],
            "ocr": [
                item
                for item in records
                if item.get("category") in {"slide", "board", "no_text"}
            ],
            "structure": [item for item in records if "expected" in item],
        }
    )
    # The stage-11 perception track was expanded from 30 to 120 vision cases so the
    # label metrics are stable; three of them (vision-010/020/030) still declare a
    # ``null`` standing prediction, which is the unknown boundary this test guards.
    assert report["vision"]["trial_count"] == 120
    assert report["vision"]["unknown_rate_by_label"]["standing"] == pytest.approx(3 / 120)
    assert report["ocr"]["no_text_false_positive_rate"] == 0


def test_retrieval_and_citation_security_metrics() -> None:
    cases = _jsonl("retrieval.v1.jsonl")
    results = {
        item["case_id"]: {
            "ranked_chunk_ids": item["expected_chunk_ids"],
            "workspace_ids": [item["workspace_id"]],
        }
        for item in cases
    }
    report = evaluate_retrieval(cases, results)
    assert report["recall@5"] == 1
    assert report["workspace_leak_rate"] == 0


def test_agent_cases_forbid_transcription_on_no_audio() -> None:
    cases = [
        AgentCase.model_validate(
            {
                "case_id": "video-no-audio-001",
                "goal": "inspect",
                "capabilities": {"vlm": True, "asr": True},
                "expected_tools": ["inspect_media"],
                "forbidden_tools": ["transcribe_audio"],
                "expected_terminal_status": "SUCCEEDED",
                "required_constraints": ["speech_metrics_unknown"],
                "split": "test",
                "dataset_version": "agent-cases.v1",
            }
        )
    ]
    report = evaluate_agent_cases(
        cases,
        lambda _case: {
            "route": "media",
            "tools": ["inspect_media"],
            "terminal_status": "SUCCEEDED",
            "steps": 1,
            "evidence_coverage": 1.0,
        },
    )
    assert report["forbidden_tool_rate"] == 0
    assert report["task_completion_rate"] == 1
