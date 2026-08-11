"""Six-label visual observation with system-owned frame provenance."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, ValidationError, model_validator

from packages.model_gateway.contracts import InvocationContext, StructuredVisionRequest
from packages.model_gateway.interfaces import StructuredVisionModel

from .sampling import SampledFrame

VISION_POLICY_VERSION = "observable-classroom-labels.v1"
ObservableLabel = Literal[
    "raise_hand",
    "standing",
    "reading_or_writing_visible",
    "group_discussion_visible",
    "teacher_at_podium",
    "teacher_patrolling_visible",
]
ObservationRegion = Literal["front", "middle", "back", "teacher_zone"]

ALLOWED_LABELS: tuple[str, ...] = (
    "raise_hand",
    "standing",
    "reading_or_writing_visible",
    "group_discussion_visible",
    "teacher_at_podium",
    "teacher_patrolling_visible",
)
_TEACHER_LABELS = {"teacher_at_podium", "teacher_patrolling_visible"}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class ObservableLabelCount(_StrictModel):
    label: ObservableLabel
    count: NonNegativeInt | None
    regions: list[ObservationRegion] = Field(default_factory=list, max_length=4)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_count_and_regions(self) -> ObservableLabelCount:
        if len(self.regions) != len(set(self.regions)):
            raise ValueError("observation regions must be unique")
        if self.label in _TEACHER_LABELS and self.count is not None and self.count > 1:
            raise ValueError("teacher presence labels are binary counts")
        if self.count in {None, 0} and self.regions:
            raise ValueError("unknown or zero count cannot claim a visible region")
        if self.count is not None and self.count > 0 and not self.regions:
            raise ValueError("positive count needs at least one visible region")
        if any(not item.strip() for item in self.evidence):
            raise ValueError("visual evidence strings must be nonempty")
        return self


class LimitedVisionInference(_StrictModel):
    visible_person_count: NonNegativeInt | None
    labels: list[ObservableLabelCount] = Field(min_length=6, max_length=6)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_limited_vocabulary(self) -> LimitedVisionInference:
        received = [item.label for item in self.labels]
        if len(received) != len(set(received)) or set(received) != set(ALLOWED_LABELS):
            raise ValueError("each of the six allowed labels must appear exactly once")
        if self.visible_person_count is not None:
            for item in self.labels:
                if (
                    item.label not in _TEACHER_LABELS
                    and item.count is not None
                    and item.count > self.visible_person_count
                ):
                    raise ValueError("observable count cannot exceed visible_person_count")
        if any(not item.strip() for item in self.limitations):
            raise ValueError("limitations must be nonempty strings")
        return self


class LimitedFrameObservation(_StrictModel):
    frame_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    global_timestamp_ms: NonNegativeInt
    sampling_policy_version: str = Field(min_length=1)
    observation_policy_version: str = VISION_POLICY_VERSION
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    inference: LimitedVisionInference


class LimitedFrameObserver:
    """Validate model output while taking asset, region-time, and frame IDs from the system."""

    def __init__(self, model: StructuredVisionModel) -> None:
        self._model = model

    def observe(
        self,
        frame: SampledFrame,
        *,
        context: InvocationContext | None = None,
    ) -> LimitedFrameObservation:
        invocation = context or InvocationContext(
            prompt_version=VISION_POLICY_VERSION,
            config_version=VISION_POLICY_VERSION,
            timeout_seconds=60.0,
            max_output_tokens=1024,
        )
        request = StructuredVisionRequest(
            image_refs=[frame.object_ref],
            instruction=_instruction(),
            response_schema=LimitedVisionInference.model_json_schema(),
            schema_name="observable_classroom_labels_v1",
            context=invocation,
        )
        result = self._model.observe_structured(request)
        try:
            inference = LimitedVisionInference.model_validate(result.parsed.structured)
        except ValidationError as exc:
            raise ValueError("VLM output failed the limited observable-label contract") from exc
        return LimitedFrameObservation(
            frame_id=frame.frame_id,
            asset_id=frame.asset_id,
            camera_id=frame.camera_id,
            global_timestamp_ms=frame.global_timestamp_ms,
            sampling_policy_version=frame.sampling_policy_version,
            model_provider=result.metadata.provider,
            model_name=result.metadata.model,
            model_revision=result.metadata.model_revision,
            inference=inference,
        )


def _instruction() -> str:
    labels = ", ".join(ALLOWED_LABELS)
    return (
        "Inspect only this sampled frame. Return exactly these six directly observable labels: "
        f"{labels}. Use count=null when visibility is insufficient. Regions must be front, middle, "
        "back, or teacher_zone. Do not infer identity, emotion, attention, motivation, ability, "
        "diagnosis, discipline, speaker role, or whole-lesson quality. A sampled occurrence is not "
        "a duration estimate."
    )
