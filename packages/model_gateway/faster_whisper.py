"""Optional local faster-whisper adapter behind the phase-4 ASR Protocol."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from time import perf_counter
from typing import Any

from .contracts import (
    AsrOutput,
    AsrRequest,
    AsrResult,
    AsrSegment,
    InvocationMetadata,
    ModelUsage,
)
from .raw_responses import RawResponseSink


class FasterWhisperAdapter:
    """Load only an explicitly selected model; no paid or large default is chosen."""

    provider = "faster-whisper-local"

    def __init__(
        self,
        *,
        model_name_or_path: str | Path,
        raw_response_sink: RawResponseSink,
        device: str = "cpu",
        compute_type: str = "int8",
        model: Any | None = None,
    ) -> None:
        if not str(model_name_or_path).strip():
            raise ValueError("an explicit faster-whisper model name or path is required")
        self._model_name = str(model_name_or_path)
        self._raw_sink = raw_response_sink
        if model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError("install the media-models optional dependency") from exc
            model = WhisperModel(self._model_name, device=device, compute_type=compute_type)
        self._model = model

    def transcribe(self, request: AsrRequest) -> AsrResult:
        audio = Path(request.audio_ref).resolve(strict=True)
        started = perf_counter()
        raw_segments, info = self._model.transcribe(
            str(audio),
            language=request.language,
            beam_size=5,
            vad_filter=False,
            word_timestamps=False,
        )
        segments = [
            AsrSegment(
                start_seconds=max(0.0, float(item.start)),
                end_seconds=max(0.0, float(item.end)),
                text=str(item.text).strip(),
            )
            for item in raw_segments
            if str(item.text).strip() and float(item.end) > float(item.start)
        ]
        language = str(getattr(info, "language", None) or request.language)
        payload = AsrOutput(language=language, segments=segments)
        raw_ref = self._raw_sink.put(
            json.dumps(payload.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
        )
        duration = _wav_duration(audio)
        return AsrResult(
            metadata=InvocationMetadata(
                provider=self.provider,
                model=self._model_name,
                model_revision=_revision(self._model, self._model_name),
                prompt_version=request.context.prompt_version,
                config_version=request.context.config_version,
                latency_ms=round((perf_counter() - started) * 1000, 3),
                usage=ModelUsage(audio_seconds=duration, cost_usd=0.0),
                raw_response_ref=raw_ref,
                provider_request_id=None,
            ),
            parsed=payload,
        )


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def _revision(model: Any, configured_name: str) -> str:
    for name in ("model_path", "model_size_or_path", "model_name_or_path"):
        value = getattr(model, name, None)
        if value:
            return str(value)
    return f"configured:{configured_name}"
