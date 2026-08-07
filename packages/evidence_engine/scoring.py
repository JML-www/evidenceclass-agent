"""Pure sourced-rubric scoring rules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Normalize non-negative weights; an all-zero mapping has no scoring meaning."""
    clean: dict[str, float] = {}
    for key, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError("weights must contain non-negative numbers")
        clean[str(key)] = float(value)
    total = sum(clean.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in clean.items()}


def weighted_score(
    metrics: Mapping[str, float | None], weights: Mapping[str, float]
) -> float | None:
    """Calculate a 0..100 score only when every positively weighted metric is known."""
    normalized = normalize_weights(weights)
    if not normalized or any(
        metrics.get(key) is None and weight > 0 for key, weight in normalized.items()
    ):
        return None
    score = sum(float(metrics[key]) * weight for key, weight in normalized.items())
    return round(max(0.0, min(100.0, score)), 1)


def missed_targets(metrics: Mapping[str, float | None], targets: Mapping[str, Any]) -> list[str]:
    """Return target keys whose observed values fall outside an explicit range."""
    missed = []
    for metric, rule in targets.items():
        value = metrics.get(metric)
        if value is None:
            continue
        below_minimum = "min" in rule and value < float(rule["min"])
        above_maximum = "max" in rule and value > float(rule["max"])
        if below_minimum or above_maximum:
            missed.append(metric)
    return missed
