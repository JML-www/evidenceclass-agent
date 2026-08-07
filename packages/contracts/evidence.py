"""Evidence and provenance contracts."""

from typing import Literal

from pydantic import Field, NonNegativeFloat, model_validator

from .base import BaseContract


class EvidenceItem(BaseContract):
    """A factual claim that can be traced to media, transcript, OCR, or knowledge."""

    evidence_id: str = Field(min_length=1, description="Unique evidence identifier.")
    source_type: Literal["image", "video", "transcript", "ocr", "knowledge"] = Field(
        description="Evidence source category."
    )
    source_ref: str = Field(
        min_length=1, description="Object key, segment id, or knowledge chunk id."
    )
    fact: str = Field(min_length=1, description="Observable fact; no unsupported inference.")
    timestamp_start_sec: NonNegativeFloat | None = Field(
        default=None, description="Evidence start timestamp in seconds."
    )
    timestamp_end_sec: NonNegativeFloat | None = Field(
        default=None, description="Evidence end timestamp in seconds."
    )
    limitations: list[str] = Field(
        default_factory=list, description="Known visibility, sampling, or model limitations."
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Evidence confidence in 0..1, or null."
    )

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> "EvidenceItem":
        if (
            self.timestamp_start_sec is not None
            and self.timestamp_end_sec is not None
            and self.timestamp_end_sec < self.timestamp_start_sec
        ):
            raise ValueError("timestamp_end_sec cannot precede timestamp_start_sec")
        return self
