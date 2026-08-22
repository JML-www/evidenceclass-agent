from datetime import timedelta
from typing import Literal

from pydantic import Field, NonNegativeFloat, PositiveFloat, ValidationInfo, field_validator

from .base import BaseContract

Visibility = Literal["visible", "partial", "not_visible"]


class TimeWindowConfig(BaseContract):
    """A sampled media window. All time values are seconds from media start."""

    start_offset_sec: NonNegativeFloat = Field(
        description="Window start offset in seconds from the media start."
    )
    duration_sec: PositiveFloat = Field(description="Window duration in seconds.")
    step_sec: PositiveFloat = Field(default=1.0, description="Sampling step in seconds.")

    @field_validator("step_sec")
    @classmethod
    def validate_step_within_window(cls, value: float, info: ValidationInfo) -> float:
        duration_sec = info.data.get("duration_sec")
        if duration_sec is not None and value > duration_sec:
            raise ValueError("step_sec must not exceed duration_sec")
        return value

    @property
    def duration_timedelta(self) -> timedelta:
        return timedelta(seconds=self.duration_sec)


class VisibleRegionRule(BaseContract):
    """Region policy supplied by the caller; area ratio is normalized to 0..1."""

    region_id: str = Field(min_length=1, description="Stable anonymous region identifier.")
    min_area_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum visible area ratio, normalized to 0..1.",
    )
    visibility: Visibility = Field(
        default="visible", description="Expected visibility state for this region."
    )
    enable_behavior_count: bool = Field(
        default=True, description="Whether behavior counts may be emitted for this region."
    )


class MetricSwitch(BaseContract):
    """Feature gates for deterministic metrics."""

    enable_overlap_count: bool = Field(default=True, description="Enable overlap counts.")
    enable_talk_duration: bool = Field(default=True, description="Enable talk duration.")
    enable_student_participation: bool = Field(
        default=True, description="Enable student participation metrics."
    )


class AnalysisRequest(BaseContract):
    """Top-level analysis input shared by API, worker, and agent planner."""

    task_id: str = Field(min_length=1, description="Opaque task identifier.")
    course_tag: str = Field(min_length=1, description="Anonymous course label.")
    is_image_mode: bool = Field(description="True for a single-image observation.")
    time_window: TimeWindowConfig = Field(description="Requested observation window.")
    regions: list[VisibleRegionRule] = Field(
        min_length=1, description="Regions allowed to produce observations."
    )
    metrics: MetricSwitch = Field(description="Enabled deterministic metric switches.")
    shard_ids: list[str] | None = Field(
        default=None, description="Video shard references; absent for image mode."
    )
    lesson_duration_sec: NonNegativeFloat | None = Field(
        default=None,
        description="Whole-lesson duration in seconds; unavailable for image mode.",
    )

    @field_validator("shard_ids")
    @classmethod
    def validate_image_shards(
        cls, value: list[str] | None, info: ValidationInfo
    ) -> list[str] | None:
        if info.data.get("is_image_mode") is True and value:
            raise ValueError("shard_ids are unavailable in image mode")
        return value

    @field_validator("lesson_duration_sec")
    @classmethod
    def validate_image_duration(cls, value: float | None, info: ValidationInfo) -> float | None:
        if info.data.get("is_image_mode") is True and value is not None:
            raise ValueError("lesson_duration_sec is unavailable in image mode")
        return value
