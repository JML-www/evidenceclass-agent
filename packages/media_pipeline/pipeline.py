"""Composable phase-5 path from safe probe to timestamped multimodal outputs."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from packages.model_gateway.interfaces import AsrModel, OcrModel, StructuredVisionModel

from .audio import AsrPipeline, AudioExtractor, EnergyVadChunker, TranscriptDocument
from .ocr import OcrBatch, OcrPipeline
from .probe import MediaProbe, SafeMediaProbe
from .sampling import ReproducibleFrameSampler, SampledFrame, SamplingPolicy
from .vision import LimitedFrameObservation, LimitedFrameObserver

MEDIA_PIPELINE_VERSION = "real-media-pipeline.v1"


class MediaPipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)

    pipeline_version: str = MEDIA_PIPELINE_VERSION
    asset_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    probe: MediaProbe
    frames: list[SampledFrame]
    transcript: TranscriptDocument | None
    ocr: OcrBatch | None
    visual_observations: list[LimitedFrameObservation]
    unavailable_outputs: list[str]


class Stage5MediaPipeline:
    def __init__(
        self,
        *,
        probe: SafeMediaProbe,
        sampler: ReproducibleFrameSampler,
        audio_extractor: AudioExtractor,
        vad_chunker: EnergyVadChunker,
        asr_model: AsrModel | None = None,
        ocr_model: OcrModel | None = None,
        vision_model: StructuredVisionModel | None = None,
        ocr_confidence_threshold: float = 0.6,
        ocr_threshold_selection_note: str = "Selected on the versioned phase-5 trial fixture.",
    ) -> None:
        self._probe = probe
        self._sampler = sampler
        self._audio_extractor = audio_extractor
        self._vad = vad_chunker
        self._asr = AsrPipeline(asr_model) if asr_model is not None else None
        self._ocr = (
            OcrPipeline(
                ocr_model,
                confidence_threshold=ocr_confidence_threshold,
                threshold_selection_note=ocr_threshold_selection_note,
            )
            if ocr_model is not None
            else None
        )
        self._vision = LimitedFrameObserver(vision_model) if vision_model is not None else None

    def run(
        self,
        source: str | Path,
        *,
        asset_id: str,
        camera_id: str,
        allowed_root: Path | None = None,
        global_offset_ms: int = 0,
        sampling_policy: SamplingPolicy | None = None,
    ) -> MediaPipelineResult:
        media = self._probe.inspect(source, allowed_root=allowed_root)
        frames = self._sampler.sample(
            source,
            probe=media,
            asset_id=asset_id,
            camera_id=camera_id,
            global_offset_ms=global_offset_ms,
            policy=sampling_policy,
        )
        unavailable: list[str] = []
        transcript = None
        extracted = self._audio_extractor.extract(source, probe=media, asset_id=asset_id)
        if extracted is None:
            unavailable.append("asr:no_audio_track")
        elif self._asr is None:
            unavailable.append("asr:model_not_configured")
        else:
            chunks = self._vad.chunk(extracted)
            transcript = self._asr.transcribe(
                chunks,
                language="zh",
                global_offset_ms=global_offset_ms,
            )
        ocr = self._ocr.recognize(frames) if self._ocr is not None else None
        if self._ocr is None:
            unavailable.append("ocr:model_not_configured")
        observations = (
            [self._vision.observe(frame) for frame in frames] if self._vision is not None else []
        )
        if self._vision is None:
            unavailable.append("vision:model_not_configured")
        return MediaPipelineResult(
            asset_id=asset_id,
            camera_id=camera_id,
            probe=media,
            frames=frames,
            transcript=transcript,
            ocr=ocr,
            visual_observations=observations,
            unavailable_outputs=unavailable,
        )
