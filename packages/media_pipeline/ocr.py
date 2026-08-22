"""OCR provenance, threshold policy, and three-category evaluation-ready output."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.model_gateway.contracts import InvocationContext, OcrRequest
from packages.model_gateway.interfaces import OcrModel

from .sampling import SampledFrame

OCR_POLICY_VERSION = "ocr-filter.v1"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class NormalizedOcrBox(_StrictModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_extent(self) -> NormalizedOcrBox:
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("OCR box exceeds normalized image bounds")
        return self


class OcrEvidenceItem(_StrictModel):
    item_id: str = Field(min_length=1)
    frame_id: str = Field(min_length=1)
    global_timestamp_ms: int = Field(ge=0)
    raw_text: str = Field(min_length=1)
    filtered_text: str | None
    included: bool
    confidence: float = Field(ge=0.0, le=1.0)
    box: NormalizedOcrBox

    @model_validator(mode="after")
    def validate_filter_state(self) -> OcrEvidenceItem:
        if self.included != (self.filtered_text is not None):
            raise ValueError("included and filtered_text must agree")
        return self


class OcrBatch(_StrictModel):
    policy_version: str = OCR_POLICY_VERSION
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    threshold_selection_note: str = Field(min_length=1)
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    items: list[OcrEvidenceItem]
    all_below_threshold: bool

    @model_validator(mode="after")
    def preserve_low_confidence_signal(self) -> OcrBatch:
        expected = bool(self.items) and not any(item.included for item in self.items)
        if self.all_below_threshold != expected:
            raise ValueError("all_below_threshold must describe the retained raw OCR items")
        return self


class OcrPipeline:
    def __init__(
        self,
        model: OcrModel,
        *,
        confidence_threshold: float,
        threshold_selection_note: str,
    ) -> None:
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("OCR threshold must be in 0..1")
        if not threshold_selection_note.strip():
            raise ValueError("OCR threshold needs a validation-set selection note")
        self._model = model
        self._threshold = confidence_threshold
        self._selection_note = threshold_selection_note.strip()

    def recognize(
        self,
        frames: list[SampledFrame],
        *,
        context: InvocationContext | None = None,
    ) -> OcrBatch:
        if not frames:
            raise ValueError("at least one sampled frame is required for OCR")
        invocation = context or InvocationContext(
            prompt_version="ocr-frame-text.v1",
            config_version=OCR_POLICY_VERSION,
            timeout_seconds=60.0,
            max_output_tokens=4096,
        )
        by_ref = {frame.object_ref: frame for frame in frames}
        result = self._model.recognize(OcrRequest(image_refs=list(by_ref), context=invocation))
        items: list[OcrEvidenceItem] = []
        for index, item in enumerate(result.parsed.items, start=1):
            frame = by_ref.get(item.image_ref)
            if frame is None:
                raise ValueError("OCR provider returned an item for an unrequested frame")
            raw_text = item.text.strip()
            if not raw_text:
                continue
            included = item.confidence >= self._threshold
            item_hash = hashlib.sha256(
                f"{frame.frame_id}|{index}|{raw_text}|{item.box.model_dump_json()}".encode()
            ).hexdigest()[:20]
            items.append(
                OcrEvidenceItem(
                    item_id=f"ocr_{item_hash}",
                    frame_id=frame.frame_id,
                    global_timestamp_ms=frame.global_timestamp_ms,
                    raw_text=raw_text,
                    filtered_text=raw_text if included else None,
                    included=included,
                    confidence=item.confidence,
                    box=NormalizedOcrBox(**item.box.model_dump()),
                )
            )
        return OcrBatch(
            confidence_threshold=self._threshold,
            threshold_selection_note=self._selection_note,
            model_provider=result.metadata.provider,
            model_name=result.metadata.model,
            model_revision=result.metadata.model_revision,
            items=items,
            all_below_threshold=bool(items) and not any(item.included for item in items),
        )


OcrTrialCategory = Literal["slide", "board", "no_text"]
