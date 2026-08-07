"""OCR output contracts with page/frame provenance."""

from pydantic import Field, NonNegativeFloat, PositiveInt, model_validator

from .base import BaseContract
from .frame import BoundingBox


class OcrBlock(BaseContract):
    """One OCR text block tied to a page or sampled frame."""

    text: str = Field(min_length=1, description="Recognized text.")
    page_number: PositiveInt | None = Field(default=None, description="1-based document page.")
    frame_time_sec: NonNegativeFloat | None = Field(
        default=None, description="Video frame timestamp in seconds."
    )
    box: BoundingBox | None = Field(
        default=None, description="Normalized OCR box in the source frame."
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="OCR confidence in 0..1, or null."
    )

    @model_validator(mode="after")
    def validate_source_reference(self) -> "OcrBlock":
        if self.page_number is None and self.frame_time_sec is None:
            raise ValueError("page_number or frame_time_sec is required for OCR provenance")
        return self
