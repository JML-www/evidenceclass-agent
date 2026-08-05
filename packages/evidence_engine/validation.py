"""Small validation rules frozen before versioned contracts are introduced."""

from __future__ import annotations

from typing import Any

IMAGE_TEMPORAL_TEACHER_EVENTS = ("questioning", "organizing_discussion")
REGION_KEYS = ("front", "middle", "back")


def _non_negative_number(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{field} must be a non-negative number or null")
    return float(value)


def validate_payload(payload: dict[str, Any]) -> None:
    """Validate the legacy image/time and region-visibility boundaries."""
    if not isinstance(payload, dict):
        raise ValueError("input root must be a JSON object")

    mode = payload.get("analysisMode")
    if mode not in {"image", "video"}:
        raise ValueError("analysisMode must be image or video")

    frames = payload.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("frames must contain at least one observation")
    if mode == "image" and len(frames) != 1:
        raise ValueError("image mode accepts exactly one observation")
    if mode == "image" and payload.get("asrSummary"):
        raise ValueError("image mode cannot contain asrSummary")
    if mode == "image" and (
        payload.get("teacherBehaviorDurations") or payload.get("teacherPositionDurations")
    ):
        raise ValueError("image mode cannot contain temporal duration summaries")

    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise ValueError(f"frames[{index}] must be an object")
        teacher = frame.get("teacher_behaviors")
        if not isinstance(teacher, dict):
            raise ValueError(f"frames[{index}].teacher_behaviors must be an object")
        if mode == "image":
            asserted = [key for key in IMAGE_TEMPORAL_TEACHER_EVENTS if teacher.get(key) is True]
            if asserted:
                raise ValueError(
                    "image mode cannot assert temporal teacher behavior: " + ", ".join(asserted)
                )

    regions = payload.get("regionHeatmap") or {}
    if not isinstance(regions, dict):
        raise ValueError("regionHeatmap must be an object")
    for key, region in regions.items():
        if key not in REGION_KEYS or not isinstance(region, dict):
            raise ValueError("regionHeatmap only accepts front, middle, and back objects")
        visibility = region.get("visibility")
        if visibility not in {"visible", "partial", "not_visible"}:
            raise ValueError(f"regionHeatmap.{key}.visibility is invalid")
        values = {
            metric: _non_negative_number(region.get(metric), f"regionHeatmap.{key}.{metric}")
            for metric in ("focus", "interaction")
        }
        if visibility == "not_visible" and any(value is not None for value in values.values()):
            raise ValueError(f"not-visible region {key} cannot contain numeric metrics")
        if any(value is not None and value > 100 for value in values.values()):
            raise ValueError(f"regionHeatmap.{key} metrics must be between 0 and 100")


def mode_capabilities(payload: dict[str, Any]) -> dict[str, bool]:
    """Describe which aggregate views the input mode can support."""
    validate_payload(payload)
    is_video = payload["analysisMode"] == "video"
    return {
        "wholeLessonMetrics": is_video,
        "timeline": is_video and len(payload["frames"]) > 1,
        "behaviorDistribution": is_video and bool(payload.get("teacherBehaviorDurations")),
        "positionDistribution": is_video and bool(payload.get("teacherPositionDurations")),
    }
