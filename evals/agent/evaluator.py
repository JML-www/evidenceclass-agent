"""Deterministic evaluator for route, tool, safety and terminal-status behaviour."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    assets: list[str] = Field(default_factory=list)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    expected_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    expected_terminal_status: str
    required_constraints: list[str] = Field(default_factory=list)
    split: str
    dataset_version: str
    evaluator_version: str = "agent-evaluator.v1"


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def evaluate_agent_cases(
    cases: list[AgentCase | Mapping[str, Any]], runner: Callable[[AgentCase], Mapping[str, Any]]
) -> dict[str, Any]:
    if not cases:
        raise ValueError("agent evaluation requires cases")
    normalized = [
        item if isinstance(item, AgentCase) else AgentCase.model_validate(item) for item in cases
    ]
    route_hits = tool_tp = tool_fp = forbidden = completed = escalated = 0
    steps: list[float] = []
    evidence: list[float] = []
    retries: list[float] = []
    citation_validity: list[float] = []
    numeric_consistency: list[float] = []
    latencies: list[float] = []
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    failures: list[str] = []
    for case in normalized:
        result = dict(runner(case))
        expected_tools = set(case.expected_tools)
        actual_tools = set(result.get("tools", []))
        route_hits += int(
            result.get("route") in result.get("expected_routes", [result.get("route")])
        )
        tool_tp += len(expected_tools & actual_tools)
        tool_fp += len(actual_tools - expected_tools)
        forbidden += len(actual_tools & set(case.forbidden_tools))
        status = str(result.get("terminal_status", ""))
        completed += int(status == case.expected_terminal_status)
        escalated += int(
            bool(result.get("human_escalated", False))
            == ("human_review" in case.required_constraints)
        )
        steps.append(float(result.get("steps", len(actual_tools))))
        evidence.append(float(result.get("evidence_coverage", 1.0 if actual_tools else 0.0)))
        retries.append(float(result.get("retry_or_repair", 0.0)))
        citation_validity.append(float(result.get("citation_validity", 1.0)))
        numeric_consistency.append(float(result.get("numeric_consistency", 1.0)))
        if result.get("latency_ms") is not None:
            latencies.append(float(result["latency_ms"]))
        total_cost += float(result.get("cost_usd", 0.0))
        total_input_tokens += int(result.get("input_tokens", 0))
        total_output_tokens += int(result.get("output_tokens", 0))
        if status != case.expected_terminal_status or forbidden:
            failures.append(case.case_id)
    denominator = max(1, tool_tp + tool_fp)
    return {
        "dataset_size": len(normalized),
        "route_accuracy": route_hits / len(normalized),
        "tool_selection_precision": tool_tp / denominator,
        "tool_selection_recall": tool_tp / max(1, sum(len(c.expected_tools) for c in normalized)),
        "forbidden_tool_rate": forbidden / len(normalized),
        "task_completion_rate": completed / len(normalized),
        "human_escalation_precision": escalated / len(normalized),
        "average_steps": sum(steps) / len(steps),
        "evidence_coverage": sum(evidence) / len(evidence),
        "retry_repair_rate": sum(retries) / len(retries),
        "citation_validity": sum(citation_validity) / len(citation_validity),
        "numeric_consistency": sum(numeric_consistency) / len(numeric_consistency),
        "latency_ms_p50": _percentile(latencies, 0.50),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "cost_usd": total_cost,
        "failed_case_ids": failures,
    }
