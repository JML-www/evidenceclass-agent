"""Region-level observation contracts."""

from typing import Any

from pydantic import Field, NonNegativeFloat, NonNegativeInt, ValidationInfo, field_validator

from .base import BaseContract
from .request import Visibility


class RegionObservation(BaseContract):
    """Aggregated observations for one region; null means unknown, not zero."""

    region_id: str = Field(min_length=1, description="Stable anonymous region identifier.")
    visibility: Visibility = Field(default="visible", description="Observed visibility state.")
    visible_student_count: NonNegativeInt | None = Field(
        default=None, description="Number of visible students in this region."
    )
    total_student_count: NonNegativeInt | None = Field(
        default=None, description="Estimated total students when available."
    )
    active_count: NonNegativeInt | None = Field(
        default=None, description="Count of students with the selected behavior."
    )
    behavior_count: NonNegativeInt | None = Field(
        default=None, description="Generic behavior count for cross-field validation."
    )
    behavior_counts: dict[str, NonNegativeInt] = Field(
        default_factory=dict, description="Per-behavior counts for this region."
    )
    total_talk_minutes: NonNegativeFloat | None = Field(
        default=None, description="Observed talk duration in minutes."
    )
    overlap_participation_rate: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Participation rate normalized to 0..1."
    )

    @field_validator(
        "visible_student_count",
        "total_student_count",
        "active_count",
        "behavior_count",
        "behavior_counts",
        "total_talk_minutes",
        "overlap_participation_rate",
    )
    @classmethod
    def validate_visibility_and_counts(cls, value: Any, info: ValidationInfo) -> Any:
        if info.data.get("visibility") == "not_visible" and value not in (None, {}):
            raise ValueError(f"{info.field_name} must be null or empty for a not_visible region")

        if info.field_name not in {"active_count", "behavior_count", "behavior_counts"}:
            return value
        visible_count = info.data.get("visible_student_count")
        if visible_count is None:
            visible_count = info.data.get("total_student_count")
        if visible_count is None or value is None:
            return value
        counts = value.values() if isinstance(value, dict) else (value,)
        if any(count > visible_count for count in counts):
            raise ValueError(f"{info.field_name} cannot exceed visible_student_count")
        return value
