"""Strict provider-neutral request and result contracts for every model capability."""

from __future__ import annotations

import math
from typing import Any, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)

MODEL_GATEWAY_SCHEMA_VERSION = "model-gateway.v0.1"


class GatewayModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class InvocationContext(GatewayModel):
    prompt_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    timeout_seconds: PositiveFloat = 30.0
    max_output_tokens: PositiveInt = 512


class ModelUsage(GatewayModel):
    input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    characters: NonNegativeInt = 0
    audio_seconds: NonNegativeFloat = 0.0
    cost_usd: NonNegativeFloat | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class InvocationMetadata(GatewayModel):
    schema_version: Literal["model-gateway.v0.1"] = MODEL_GATEWAY_SCHEMA_VERSION
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    latency_ms: NonNegativeFloat
    usage: ModelUsage
    raw_response_ref: str = Field(min_length=1)
    provider_request_id: str | None = None


ParsedT = TypeVar("ParsedT")


class CapabilityResult(GatewayModel, Generic[ParsedT]):
    metadata: InvocationMetadata
    parsed: ParsedT


class ChatMessage(GatewayModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(GatewayModel):
    messages: list[ChatMessage] = Field(min_length=1)
    context: InvocationContext
    response_schema: dict[str, Any]
    schema_name: str = Field(default="chat_response", pattern=r"^[A-Za-z0-9_-]+$")


class ChatOutput(GatewayModel):
    text: str
    structured: dict[str, Any] = Field(default_factory=dict)


class RegionEstimate(GatewayModel):
    region_id: Literal["front", "middle", "back"]
    visibility: Literal["visible", "partial", "not_visible"]
    focus: float | None = Field(default=None, ge=0.0, le=100.0)
    interaction: float | None = Field(default=None, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_visibility(self) -> RegionEstimate:
        if self.visibility == "not_visible" and (
            self.focus is not None or self.interaction is not None
        ):
            raise ValueError("not-visible region cannot contain numeric estimates")
        return self


class TeacherObservation(GatewayModel):
    teaching: bool
    blackboard_writing: bool
    patrolling: bool
    questioning: bool | None = None
    organizing_discussion: bool | None = None
    guiding_students: bool
    using_slides: bool


class VisionObservation(GatewayModel):
    frame_id: str = Field(min_length=1)
    visible_student_count: NonNegativeInt
    focused: NonNegativeInt
    head_down_reading_or_writing: NonNegativeInt
    hand_raised: NonNegativeInt
    discussion: NonNegativeInt
    distracted: NonNegativeInt
    teacher: TeacherObservation
    evidence: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("evidence", "limitations")
    @classmethod
    def validate_nonempty_text(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("items must be non-empty")
        return values

    @model_validator(mode="after")
    def validate_behavior_bounds(self) -> VisionObservation:
        counts = (
            self.focused,
            self.head_down_reading_or_writing,
            self.hand_raised,
            self.discussion,
            self.distracted,
        )
        if any(count > self.visible_student_count for count in counts):
            raise ValueError("behavior count cannot exceed visible_student_count")
        return self


class VisionRequest(GatewayModel):
    image_refs: list[str] = Field(min_length=1, max_length=20)
    instruction: str = Field(min_length=1)
    context: InvocationContext


class VisionOutput(GatewayModel):
    observation: VisionObservation
    regions: list[RegionEstimate] = Field(default_factory=list, max_length=3)

    @field_validator("regions")
    @classmethod
    def validate_unique_regions(cls, regions: list[RegionEstimate]) -> list[RegionEstimate]:
        ids = [region.region_id for region in regions]
        if len(ids) != len(set(ids)):
            raise ValueError("region_id must be unique")
        return regions


class StructuredVisionRequest(GatewayModel):
    """Vision request whose business-owned Schema is validated again by its consumer."""

    image_refs: list[str] = Field(min_length=1, max_length=20)
    instruction: str = Field(min_length=1)
    response_schema: dict[str, Any]
    schema_name: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    context: InvocationContext


class StructuredVisionOutput(GatewayModel):
    structured: dict[str, Any]


class AsrRequest(GatewayModel):
    audio_ref: str = Field(min_length=1)
    language: str = Field(min_length=1)
    context: InvocationContext


class AsrSegment(GatewayModel):
    start_seconds: NonNegativeFloat
    end_seconds: NonNegativeFloat
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_order(self) -> AsrSegment:
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds cannot precede start_seconds")
        return self


class AsrOutput(GatewayModel):
    language: str = Field(min_length=1)
    segments: list[AsrSegment]


class OcrRequest(GatewayModel):
    image_refs: list[str] = Field(min_length=1, max_length=100)
    context: InvocationContext


class OcrBox(GatewayModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_extent(self) -> OcrBox:
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("OCR box must stay within normalized image bounds")
        return self


class OcrItem(GatewayModel):
    image_ref: str = Field(min_length=1)
    text: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    box: OcrBox


class OcrOutput(GatewayModel):
    items: list[OcrItem]


class EmbeddingRequest(GatewayModel):
    texts: list[str] = Field(min_length=1, max_length=256)
    context: InvocationContext

    @field_validator("texts")
    @classmethod
    def validate_texts(cls, texts: list[str]) -> list[str]:
        if any(not text.strip() for text in texts):
            raise ValueError("embedding texts must be non-empty")
        return texts


class EmbeddingOutput(GatewayModel):
    vectors: list[list[float]] = Field(min_length=1)

    @field_validator("vectors")
    @classmethod
    def validate_vectors(cls, vectors: list[list[float]]) -> list[list[float]]:
        if any(not vector for vector in vectors):
            raise ValueError("embedding vectors must be non-empty")
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise ValueError("embedding vectors must contain finite numbers")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise ValueError("embedding vectors must have one dimension")
        return vectors


class RerankRequest(GatewayModel):
    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1, max_length=256)
    top_n: PositiveInt
    context: InvocationContext

    @model_validator(mode="after")
    def validate_top_n(self) -> RerankRequest:
        if self.top_n > len(self.documents):
            raise ValueError("top_n cannot exceed document count")
        return self


class RerankedItem(GatewayModel):
    original_index: NonNegativeInt
    score: float = Field(ge=0.0, le=1.0)


class RerankOutput(GatewayModel):
    items: list[RerankedItem]


ChatResult = CapabilityResult[ChatOutput]
VisionResult = CapabilityResult[VisionOutput]
StructuredVisionResult = CapabilityResult[StructuredVisionOutput]
AsrResult = CapabilityResult[AsrOutput]
OcrResult = CapabilityResult[OcrOutput]
EmbeddingResult = CapabilityResult[EmbeddingOutput]
RerankResult = CapabilityResult[RerankOutput]


def vision_output_to_engine_payload(output: VisionOutput) -> dict[str, Any]:
    """Translate validated fake/real VLM output into the phase-2 deterministic boundary."""

    observation = output.observation
    regions = {
        region.region_id: {
            "visibility": region.visibility,
            "focus": region.focus,
            "interaction": region.interaction,
        }
        for region in output.regions
    }
    return {
        "analysisMode": "image",
        "courseInfo": {
            "courseName": "Synthetic model-gateway acceptance",
            "className": "Synthetic class",
            "chapter": "Fake adapter E2E",
            "lessonTime": "current image",
            "studentCount": observation.visible_student_count,
        },
        "observationGoal": "Describe only visible facts from an authorized synthetic input.",
        "sourceFiles": [{"name": "fixture-image", "type": "image"}],
        "frames": [
            {
                "frame_id": observation.frame_id,
                "time": "current image",
                "visible_student_count": observation.visible_student_count,
                "student_behaviors": {
                    "focused": observation.focused,
                    "head_down_reading_or_writing": observation.head_down_reading_or_writing,
                    "hand_raised": observation.hand_raised,
                    "discussion": observation.discussion,
                    "distracted": observation.distracted,
                },
                "teacher_behaviors": observation.teacher.model_dump(),
                "classroom_stage": "current image",
                "evidence": observation.evidence,
                "limitations": observation.limitations,
                "confidence": observation.confidence,
            }
        ],
        "regionHeatmap": regions,
    }
