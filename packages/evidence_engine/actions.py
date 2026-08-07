"""Evidence-linked action and retest suggestions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

ACTION_RULES = (
    (
        "focus",
        "Use a short attention check tied to the current learning objective.",
        "Repeat the same sampling protocol and compare the focus percentage.",
    ),
    (
        "participation",
        "Add a structured participation turn with an explicit response window.",
        "Compare the participation percentage at the same lesson stage.",
    ),
    (
        "interaction",
        "Insert a clearly timed peer or teacher-student interaction prompt.",
        "Re-observe interaction under the same camera coverage and duration.",
    ),
)


def build_actions(
    metrics: Mapping[str, float | None], evidence_ids: Sequence[str]
) -> list[dict[str, object]]:
    """Create deterministic suggestions; no action claims an unobserved improvement."""
    actions = []
    for index, (metric_key, suggestion, retest) in enumerate(ACTION_RULES, start=1):
        actions.append(
            {
                "actionId": f"A-{index:03d}",
                "metricKey": metric_key,
                "currentValue": metrics.get(metric_key),
                "suggestion": suggestion,
                "retest": retest,
                "evidenceIds": list(evidence_ids[:3]),
            }
        )
    return actions
