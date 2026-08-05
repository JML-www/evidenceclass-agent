"""Pure metric formulas protected by the v3.1 characterization tests."""

from __future__ import annotations

from typing import Any

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


def frame_metrics(
    frame: dict[str, Any], fallback_total: int, mode: str = "video"
) -> dict[str, float | None]:
    """Calculate descriptive metrics for one observation without double-counting people."""
    total = int(
        frame.get("visible_student_count")
        or frame.get("estimated_total_students")
        or fallback_total
    )
    if total <= 0:
        raise ValueError("visible student count must be positive")

    students = frame["student_behaviors"]
    teacher = frame["teacher_behaviors"]
    focused = _numeric(students, "focused")
    writing = _numeric(students, "head_down_reading_or_writing")
    hands = _numeric(students, "hand_raised")
    discussion = _numeric(students, "discussion")

    focus = _rounded(min(100.0, focused / total * 100)) if focused is not None else None
    participation_count = _behavior_lower_bound([hands, discussion, writing])
    interaction_count = _behavior_lower_bound([hands, discussion])
    participation = (
        _rounded(min(100.0, participation_count / total * 100))
        if participation_count is not None
        else None
    )
    interaction = (
        _rounded(min(100.0, interaction_count / total * 100))
        if interaction_count is not None
        else None
    )
    guidance_observed = teacher.get("patrolling") is True or teacher.get("guiding_students") is True
    guidance = 100.0 if guidance_observed else (0.0 if mode == "video" else None)
    attention_count = _behavior_lower_bound(
        [
            _numeric(students, key)
            for key in ("phone_use", "sleeping_or_desk_down", "left_seat", "distracted")
            if key in students
        ]
    )
    abnormal = (
        _rounded(min(100.0, attention_count / total * 100)) if attention_count is not None else None
    )
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


def percentage_distribution(durations: dict[str, float]) -> dict[str, float]:
    """Convert non-negative duration values into stable percentages."""
    if any(isinstance(value, bool) or value < 0 for value in durations.values()):
        raise ValueError("durations must contain non-negative numbers")
    total = sum(float(value) for value in durations.values())
    if total <= 0:
        return {}
    return {key: round(float(value) / total * 100, 1) for key, value in durations.items()}


def evaluate_rubric(metrics: dict[str, float | None], rubric: dict[str, Any]) -> dict[str, Any]:
    """Apply a named, sourced rubric without inventing default weights or targets."""
    for field in ("name", "version", "source"):
        if not str(rubric.get(field, "")).strip():
            raise ValueError(f"rubric.{field} is required")

    supplied_weights = rubric.get("weights") or {}
    if any(key not in COMPOSITE_KEYS for key in supplied_weights):
        raise ValueError("rubric contains an unsupported scoring metric")
    weights = {key: float(supplied_weights.get(key, 0)) for key in COMPOSITE_KEYS}
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("rubric weights must sum to more than zero")
    if any(metrics.get(key) is None and weight > 0 for key, weight in weights.items()):
        overall = None
    else:
        overall = _rounded(
            sum(float(metrics[key]) * weight for key, weight in weights.items()) / total_weight
        )

    missed_targets = []
    for metric, rule in (rubric.get("targets") or {}).items():
        value = metrics.get(metric)
        if value is None:
            continue
        below_minimum = "min" in rule and value < float(rule["min"])
        above_maximum = "max" in rule and value > float(rule["max"])
        if below_minimum or above_maximum:
            missed_targets.append(metric)

    return {
        "overall": overall,
        "source": rubric["source"],
        "missedTargets": missed_targets,
    }
