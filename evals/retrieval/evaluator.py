"""Versioned retrieval and citation evaluator with workspace-security gates."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def _rank_metrics(expected: set[str], ranked: list[str], k: int) -> tuple[float, float, float]:
    if not expected:
        raise ValueError("expected chunk ids cannot be empty")
    top = ranked[:k]
    recall = len(set(top) & expected) / len(expected)
    positions = [i for i, chunk_id in enumerate(ranked, 1) if chunk_id in expected]
    mrr = 1 / positions[0] if positions else 0.0
    dcg = sum(1 / math.log2(i + 1) for i, chunk_id in enumerate(top, 1) if chunk_id in expected)
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(k, len(expected)) + 1))
    return recall, mrr, dcg / ideal if ideal else 0.0


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def evaluate_retrieval_cases(
    cases: list[Mapping[str, Any]], results: Mapping[str, Mapping[str, Any]], *, k: int = 5
) -> dict[str, Any]:
    if not cases:
        raise ValueError("retrieval evaluation requires cases")
    recalls: list[float] = []
    mrrs: list[float] = []
    ndcgs: list[float] = []
    failures: list[str] = []
    workspace_leaks = 0
    latencies: list[float] = []
    costs: list[float] = []
    input_tokens = 0
    output_tokens = 0
    for case in cases:
        case_id = str(case["case_id"])
        expected = set(case.get("expected_chunk_ids", []))
        result = results.get(case_id, {})
        ranked = [str(item) for item in result.get("ranked_chunk_ids", [])]
        recall, mrr, ndcg = _rank_metrics(expected, ranked, k)
        recalls.append(recall)
        mrrs.append(mrr)
        ndcgs.append(ndcg)
        if recall < 1:
            failures.append(case_id)
        requested_workspace = str(case.get("workspace_id", ""))
        if any(str(item) != requested_workspace for item in result.get("workspace_ids", [])):
            workspace_leaks += 1
        if result.get("latency_ms") is not None:
            latencies.append(float(result["latency_ms"]))
        costs.append(float(result.get("cost_usd", 0.0)))
        input_tokens += int(result.get("input_tokens", 0))
        output_tokens += int(result.get("output_tokens", 0))
    return {
        "dataset_size": len(cases),
        f"recall@{k}": sum(recalls) / len(recalls),
        "mrr": sum(mrrs) / len(mrrs),
        f"ndcg@{k}": sum(ndcgs) / len(ndcgs),
        "failed_case_ids": failures,
        "workspace_leak_rate": workspace_leaks / len(cases),
        "latency_ms_p50": _percentile(latencies, 0.50),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": sum(costs),
    }


def evaluate_citations(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Measure citation precision/recall and groundedness without an LLM judge."""
    if not records:
        raise ValueError("citation evaluation requires records")
    precisions: list[float] = []
    recalls: list[float] = []
    grounded: list[float] = []
    refusals = 0
    invalid = 0
    for record in records:
        expected = set(record.get("expected_citation_ids", []))
        actual = set(record.get("citation_ids", []))
        valid = set(record.get("valid_citation_ids", actual))
        invalid += len(actual - valid)
        if not expected and not actual:
            precisions.append(1.0)
            recalls.append(1.0)
        else:
            precisions.append(len(actual & valid) / len(actual) if actual else 0.0)
            recalls.append(len(actual & expected) / len(expected) if expected else 0.0)
        grounded.append(float(record.get("grounded", bool(actual <= valid))))
        refusals += int(
            bool(record.get("should_refuse", False)) == bool(record.get("refused", False))
        )
    return {
        "citation_precision": sum(precisions) / len(precisions),
        "citation_recall": sum(recalls) / len(recalls),
        "answer_groundedness": sum(grounded) / len(grounded),
        "no_answer_refusal_rate": refusals / len(records),
        "invalid_citation_count": invalid,
    }


def evaluate_retrieval(
    cases: list[Mapping[str, Any]],
    results: Mapping[str, Mapping[str, Any]],
    citations: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    report = evaluate_retrieval_cases(cases, results)
    if citations is not None:
        report["citations"] = evaluate_citations(citations)
    return report
