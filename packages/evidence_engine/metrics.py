"""Pure metric formulas protected by characterization and property tests.

This module deliberately performs no file, network, database, or clock access.  A zero or
unknown denominator produces ``None`` rather than a fabricated zero percent.
"""

from __future__ import annotations

from typing import Any

from .scoring import missed_targets, normalize_weights, weighted_score

COMPOSITE_KEYS = (
    "focus",
    "participation",
    "interaction",
    "teacherGuidance",
    "teachingRhythm",
)


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 1)


def _numeric(mapping: dict[str, Any], key: str) -> float | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{key} must be a non-negative number or null")
    return float(value)


def _behavior_lower_bound(values: list[float | None]) -> float | None:
    observed = [value for value in values if value is not None]
    return max(observed) if observed else None


def safe_percentage(numerator: float | None, denominator: float | None) -> float | None:
    """Return a bounded percentage, or ``None`` when the ratio is not observable."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    if numerator < 0:
        raise ValueError("numerator must be non-negative")
    return _rounded(min(100.0, numerator / denominator * 100.0))


def frame_metrics(
    frame: dict[str, Any], fallback_total: int, mode: str = "video"
) -> dict[str, float | None]:
    """Calculate descriptive metrics for one observation without double-counting people."""
    total_value = frame.get("visible_student_count")
    if total_value is None:
        total_value = frame.get("estimated_total_students")
    if total_value is None:
        total_value = fallback_total
    if isinstance(total_value, bool) or not isinstance(total_value, (int, float)):
        raise ValueError("visible student count must be a number")
    total = float(total_value)

    students = frame["student_behaviors"]
    teacher = frame["teacher_behaviors"]
    focused = _numeric(students, "focused")
    writing = _numeric(students, "head_down_reading_or_writing")
    hands = _numeric(students, "hand_raised")
    discussion = _numeric(students, "discussion")

    focus = safe_percentage(focused, total)
    participation_count = _behavior_lower_bound([hands, discussion, writing])
    interaction_count = _behavior_lower_bound([hands, discussion])
    participation = safe_percentage(participation_count, total)
    interaction = safe_percentage(interaction_count, total)
    guidance_observed = teacher.get("patrolling") is True or teacher.get("guiding_students") is True
    guidance = 100.0 if guidance_observed else (0.0 if mode == "video" else None)
    attention_count = _behavior_lower_bound(
        [
            _numeric(students, key)
            for key in ("phone_use", "sleeping_or_desk_down", "left_seat", "distracted")
            if key in students
        ]
    )
    abnormal = safe_percentage(attention_count, total)
    return {
        "focus": focus,
        "participation": participation,
        "interaction": interaction,
        "teacherGuidance": _rounded(guidance),
        "abnormalRate": abnormal,
    }


def aggregate_metric(frames: list[dict[str, Any]], key: str) -> float | None:
    """Aggregate by observation duration; model confidence is intentionally ignored."""
    pairs = [
        (frame["metrics"].get(key), float(frame.get("observationDurationSeconds") or 1.0))
        for frame in frames
    ]
    observed = [(value, weight) for value, weight in pairs if value is not None and weight > 0]
    if not observed:
        return None
    return _rounded(
        sum(float(value) * weight for value, weight in observed)
        / sum(weight for _, weight in observed)
    )


def percentage_distribution(durations: dict[str, float]) -> dict[str, float | None]:
    """Convert durations to percentages without treating missing exposure as zero."""
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
        for value in durations.values()
    ):
        raise ValueError("durations must contain non-negative numbers")
    total = sum(float(value) for value in durations.values())
    if total <= 0:
        return dict.fromkeys(durations)
    return {key: round(float(value) / total * 100, 1) for key, value in durations.items()}


def comparable_region_values(
    regions: list[dict[str, Any]], metric_key: str
) -> list[tuple[str, float]]:
    """Return comparable values, always excluding regions that were not visible."""
    comparable = []
    for region in regions:
        if region.get("visibility") == "not_visible":
            continue
        metrics = region.get("metrics", region)
        value = metrics.get(metric_key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"region metric {metric_key} must be numeric or null")
        comparable.append((str(region.get("region_id") or region.get("regionId")), float(value)))
    return comparable


def evaluate_rubric(metrics: dict[str, float | None], rubric: dict[str, Any]) -> dict[str, Any]:
    """Apply a named, sourced rubric without inventing default weights or targets."""
    for field in ("name", "version", "source"):
        if not str(rubric.get(field, "")).strip():
            raise ValueError(f"rubric.{field} is required")

    supplied_weights = rubric.get("weights") or {}
    if any(key not in COMPOSITE_KEYS for key in supplied_weights):
        raise ValueError("rubric contains an unsupported scoring metric")
    weights = {key: supplied_weights.get(key, 0) for key in COMPOSITE_KEYS}
    normalized_weights = normalize_weights(weights)
    if not normalized_weights:
        raise ValueError("rubric weights must sum to more than zero")

    return {
        "overall": weighted_score(metrics, normalized_weights),
        "source": rubric["source"],
        "missedTargets": missed_targets(metrics, rubric.get("targets") or {}),
        "normalizedWeights": normalized_weights,
    }
