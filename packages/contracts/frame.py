"""Typed observations emitted by a vision adapter."""

from typing import Literal

from pydantic import Field, NonNegativeFloat, model_validator

from .base import BaseContract

BehaviorType = Literal["listen", "speak", "write", "interact", "idle"]


class BoundingBox(BaseContract):
    """Normalized image coordinates, where (0, 0) is the top-left corner."""

    x1: float = Field(ge=0.0, le=1.0, description="Left coordinate, normalized to 0..1.")
    y1: float = Field(ge=0.0, le=1.0, description="Top coordinate, normalized to 0..1.")
    x2: float = Field(ge=0.0, le=1.0, description="Right coordinate, normalized to 0..1.")
    y2: float = Field(ge=0.0, le=1.0, description="Bottom coordinate, normalized to 0..1.")

    @model_validator(mode="after")
    def validate_order(self) -> "BoundingBox":
        if self.x2 < self.x1:
            raise ValueError("x2 must be greater than or equal to x1")
        if self.y2 < self.y1:
            raise ValueError("y2 must be greater than or equal to y1")
        return self


class FrameObservation(BaseContract):
    """One anonymous, timestamped observation from a sampled frame."""

    frame_time_sec: NonNegativeFloat = Field(description="Frame timestamp in seconds.")
    region_id: str = Field(min_length=1, description="Anonymous region identifier.")
    student_id: str | None = Field(
        default=None, description="Anonymous subject identifier; null when not visible."
    )
    behavior: BehaviorType | None = Field(
        default=None, description="Observable behavior label; null when not visible."
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Adapter confidence in 0..1, or null."
    )
    box: BoundingBox | None = Field(
        default=None, description="Normalized subject box; null when not visible."
    )
    visible: bool = Field(default=True, description="Whether this subject is visible in the frame.")
    numeric_metrics: dict[str, NonNegativeFloat] = Field(
        default_factory=dict,
        description="Derived numeric observations; empty when the region is not visible.",
    )

    @model_validator(mode="after")
    def validate_visibility(self) -> "FrameObservation":
        if self.visible and self.behavior is None:
            raise ValueError("behavior must be present when visible")
        if not self.visible:
            populated = {
                "student_id": self.student_id,
                "behavior": self.behavior,
                "confidence": self.confidence,
                "box": self.box,
                "numeric_metrics": self.numeric_metrics,
            }
            invalid = [name for name, value in populated.items() if value not in (None, {})]
            if invalid:
                raise ValueError(
                    "invisible observation fields must be null or empty: " + ", ".join(invalid)
                )
        return self
