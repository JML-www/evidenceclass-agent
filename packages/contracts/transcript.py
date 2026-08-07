"""Speech-to-text output contracts."""

from typing import Literal

from pydantic import Field, NonNegativeFloat, model_validator

from .base import BaseContract


class TranscriptSegment(BaseContract):
    """A timestamped transcript segment; speaker identity is optional and anonymous."""

    start_sec: NonNegativeFloat = Field(description="Segment start in seconds.")
    end_sec: NonNegativeFloat = Field(description="Segment end in seconds.")
    text: str = Field(min_length=1, description="ASR text for this segment.")
    speaker_id: str | None = Field(default=None, description="Anonymous diarized speaker id.")
    speaker_role: Literal["teacher", "student", "unknown"] = Field(
        default="unknown", description="Role inferred only when supported by diarization."
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="ASR confidence in 0..1, or null."
    )

    @model_validator(mode="after")
    def validate_time_order(self) -> "TranscriptSegment":
        if self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be greater than start_sec")
        if self.speaker_role != "unknown" and self.speaker_id is None:
            raise ValueError("speaker_id is required when speaker_role is not unknown")
        return self

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec
