"""Top-level analysis result and artifact manifest contracts."""

from datetime import datetime
from typing import Literal

from pydantic import Field, NonNegativeFloat, ValidationInfo, field_validator

from .base import BaseContract
from .evidence import EvidenceItem
from .frame import FrameObservation
from .ocr import OcrBlock
from .region import RegionObservation
from .rubric import EvaluationRubric
from .transcript import TranscriptSegment


class AnalysisResult(BaseContract):
    """Published analysis result with explicit unknown and provenance boundaries."""

    task_id: str = Field(min_length=1, description="Owning analysis task identifier.")
    analysis_mode: Literal["image", "video"] = Field(description="Input analysis mode.")
    observations: list[FrameObservation] = Field(
        default_factory=list, description="Frame-level observations."
    )
    transcript_segments: list[TranscriptSegment] = Field(
        default_factory=list, description="Timestamped ASR segments."
    )
    ocr_blocks: list[OcrBlock] = Field(
        default_factory=list, description="OCR blocks with provenance."
    )
    region_observations: list[RegionObservation] = Field(
        default_factory=list, description="Aggregated region observations."
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list, description="Evidence items referenced by final claims."
    )
    rubric: EvaluationRubric | None = Field(
        default=None, description="Sourced evaluation rubric, or null when unavailable."
    )
    lesson_duration_sec: NonNegativeFloat | None = Field(
        default=None, description="Whole-lesson duration in seconds; unavailable for image mode."
    )
    observed_duration_sec: NonNegativeFloat | None = Field(
        default=None, description="Actually observed media duration in seconds."
    )
    speaker_diarization_available: bool = Field(
        default=False, description="Whether speaker identities were separated by an adapter."
    )
    teacher_speaking_ratio: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Teacher speaking ratio in 0..1; only valid with diarization.",
    )

    @field_validator("transcript_segments")
    @classmethod
    def validate_image_transcript(
        cls, value: list[TranscriptSegment], info: ValidationInfo
    ) -> list[TranscriptSegment]:
        if info.data.get("analysis_mode") == "image" and value:
            raise ValueError("transcript_segments are unavailable in image mode")
        return value

    @field_validator("lesson_duration_sec")
    @classmethod
    def validate_image_duration(cls, value: float | None, info: ValidationInfo) -> float | None:
        if info.data.get("analysis_mode") == "image" and value is not None:
            raise ValueError("lesson_duration_sec is unavailable in image mode")
        return value

    @field_validator("teacher_speaking_ratio")
    @classmethod
    def validate_teacher_ratio(cls, value: float | None, info: ValidationInfo) -> float | None:
        if value is not None and info.data.get("speaker_diarization_available") is not True:
            raise ValueError("teacher_speaking_ratio requires speaker_diarization_available")
        return value


class ArtifactManifest(BaseContract):
    """Object-store pointer for a versioned result artifact."""

    artifact_id: str = Field(min_length=1, description="Stable artifact identifier.")
    task_id: str = Field(min_length=1, description="Owning task identifier.")
    kind: Literal["analysis_result", "evidence_ledger", "report", "timeline"] = Field(
        description="Artifact category."
    )
    object_key: str = Field(min_length=1, description="Relative object-store key; no local path.")
    sha256: str = Field(
        pattern=r"^[0-9a-fA-F]{64}$", description="SHA-256 digest of the stored bytes."
    )
    version: str = Field(min_length=1, description="Artifact format version.")
    created_at: datetime = Field(description="UTC creation timestamp.")
