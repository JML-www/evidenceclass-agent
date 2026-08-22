"""16 kHz mono extraction, deterministic energy VAD, and global ASR merging."""

from __future__ import annotations

import math
import wave
from array import array
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt

from packages.model_gateway.contracts import AsrRequest, InvocationContext
from packages.model_gateway.interfaces import AsrModel

from .errors import MediaToolExecutionError
from .probe import MediaProbe
from .tools import CommandRunner, SubprocessCommandRunner, resolve_media_tool, sanitized_stderr

try:  # Python 3.13 removed audioop; the tiny fallback keeps deterministic RMS VAD portable.
    import audioop  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.13+

    class _AudioOpCompat:
        @staticmethod
        def rms(data: bytes, width: int) -> int:
            if width != 2 or len(data) < 2:
                return 0
            samples = array("h")
            samples.frombytes(data[: len(data) - len(data) % 2])
            if not samples:
                return 0
            return round(math.sqrt(sum(sample * sample for sample in samples) / len(samples)))

    audioop = _AudioOpCompat()

AUDIO_POLICY_VERSION = "audio-extraction.v1"
VAD_POLICY_VERSION = "energy-vad.v1"
ASR_MERGE_POLICY_VERSION = "asr-global-merge.v1"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class ExtractedAudio(_StrictModel):
    source_ref: str = Field(min_length=1)
    audio_ref: str = Field(min_length=1)
    duration_ms: PositiveInt
    sample_rate_hz: Literal[16000] = 16000
    channels: Literal[1] = 1
    policy_version: str = AUDIO_POLICY_VERSION


class SpeechChunk(_StrictModel):
    chunk_id: str = Field(min_length=1)
    audio_ref: str = Field(min_length=1)
    start_ms: NonNegativeInt
    end_ms: PositiveInt
    vad_policy_version: str = VAD_POLICY_VERSION


class GlobalTranscriptSegment(_StrictModel):
    start_ms: NonNegativeInt
    end_ms: PositiveInt
    text: str = Field(min_length=1)
    speaker_role: Literal["unknown"] = "unknown"
    source_chunk_id: str = Field(min_length=1)


class TranscriptDocument(_StrictModel):
    language: str = Field(min_length=1)
    segments: list[GlobalTranscriptSegment]
    model_provider: str | None = None
    model_name: str | None = None
    model_revision: str | None = None
    speaker_diarization: Literal[False] = False
    speaker_role_metrics_available: Literal[False] = False
    merge_policy_version: str = ASR_MERGE_POLICY_VERSION


class AudioExtractor:
    def __init__(
        self,
        *,
        output_root: str | Path,
        ffmpeg_path: str | Path | None = None,
        runner: CommandRunner | None = None,
        timeout_seconds: float = 180.0,
    ) -> None:
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._ffmpeg = resolve_media_tool("ffmpeg", ffmpeg_path)
        self._runner = runner or SubprocessCommandRunner()
        self._timeout = timeout_seconds

    def extract(
        self, source: str | Path, *, probe: MediaProbe, asset_id: str
    ) -> ExtractedAudio | None:
        if not probe.audio_streams:
            return None
        destination = self.output_root / f"{_component(asset_id)}.16khz-mono.wav"
        result = self._runner.run(
            (
                str(self._ffmpeg),
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(Path(source).resolve()),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ),
            timeout_seconds=self._timeout,
        )
        if result.returncode != 0 or not destination.is_file():
            raise MediaToolExecutionError(
                "audio extraction failed",
                details={"diagnostic": sanitized_stderr(result)},
            )
        with wave.open(str(destination), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getframerate() != 16000 or wav.getsampwidth() != 2:
                raise MediaToolExecutionError("extracted audio is not 16 kHz mono PCM16")
            duration_ms = max(1, round(wav.getnframes() * 1000 / wav.getframerate()))
        return ExtractedAudio(
            source_ref=Path(source).name,
            audio_ref=str(destination),
            duration_ms=duration_ms,
        )


class EnergyVadChunker:
    """A reproducible VAD/chunker; faster-whisper's own VAD remains disabled downstream."""

    def __init__(
        self,
        *,
        output_root: str | Path,
        threshold_dbfs: float = -42.0,
        frame_ms: int = 30,
        min_speech_ms: int = 240,
        merge_gap_ms: int = 300,
        pad_ms: int = 120,
        max_chunk_ms: int = 30_000,
    ) -> None:
        if frame_ms <= 0 or min_speech_ms <= 0 or merge_gap_ms < 0 or pad_ms < 0:
            raise ValueError("VAD durations are invalid")
        if max_chunk_ms < min_speech_ms:
            raise ValueError("max chunk must be at least the minimum speech duration")
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.threshold_dbfs = threshold_dbfs
        self.frame_ms = frame_ms
        self.min_speech_ms = min_speech_ms
        self.merge_gap_ms = merge_gap_ms
        self.pad_ms = pad_ms
        self.max_chunk_ms = max_chunk_ms

    def chunk(self, audio: ExtractedAudio) -> list[SpeechChunk]:
        with wave.open(audio.audio_ref, "rb") as wav:
            rate = wav.getframerate()
            width = wav.getsampwidth()
            channels = wav.getnchannels()
            frames = wav.readframes(wav.getnframes())
        if (rate, width, channels) != (16000, 2, 1):
            raise ValueError("VAD requires 16 kHz mono PCM16")
        samples_per_frame = max(1, rate * self.frame_ms // 1000)
        bytes_per_frame = samples_per_frame * width
        threshold = max(1, round(32768 * math.pow(10.0, self.threshold_dbfs / 20.0)))
        active: list[tuple[int, int]] = []
        for byte_offset in range(0, len(frames), bytes_per_frame):
            data = frames[byte_offset : byte_offset + bytes_per_frame]
            if len(data) < width:
                continue
            start_ms = byte_offset // width * 1000 // rate
            end_ms = min(audio.duration_ms, start_ms + self.frame_ms)
            if audioop.rms(data, width) >= threshold:
                active.append((start_ms, end_ms))
        intervals = self._merge(active, audio.duration_ms)
        chunks: list[SpeechChunk] = []
        for interval_start, interval_end in intervals:
            cursor = interval_start
            while cursor < interval_end:
                end = min(interval_end, cursor + self.max_chunk_ms)
                if end - cursor >= self.min_speech_ms:
                    chunks.append(
                        self._write_chunk(
                            frames,
                            rate=rate,
                            width=width,
                            start_ms=cursor,
                            end_ms=end,
                            index=len(chunks) + 1,
                        )
                    )
                cursor = end
        return chunks

    def _merge(self, active: list[tuple[int, int]], duration_ms: int) -> list[tuple[int, int]]:
        merged: list[list[int]] = []
        for start, end in active:
            if not merged or start - merged[-1][1] > self.merge_gap_ms:
                merged.append([start, end])
            else:
                merged[-1][1] = end
        padded = [
            (max(0, start - self.pad_ms), min(duration_ms, end + self.pad_ms))
            for start, end in merged
            if end - start >= self.min_speech_ms
        ]
        return padded

    def _write_chunk(
        self,
        frames: bytes,
        *,
        rate: int,
        width: int,
        start_ms: int,
        end_ms: int,
        index: int,
    ) -> SpeechChunk:
        destination = self.output_root / f"speech_{index:04d}_{start_ms}_{end_ms}.wav"
        start_byte = start_ms * rate // 1000 * width
        end_byte = end_ms * rate // 1000 * width
        with wave.open(str(destination), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(width)
            wav.setframerate(rate)
            wav.writeframes(frames[start_byte:end_byte])
        return SpeechChunk(
            chunk_id=f"speech_{index:04d}",
            audio_ref=str(destination),
            start_ms=start_ms,
            end_ms=end_ms,
        )


class AsrPipeline:
    def __init__(self, model: AsrModel) -> None:
        self._model = model

    def transcribe(
        self,
        chunks: list[SpeechChunk],
        *,
        language: str,
        global_offset_ms: int = 0,
        context: InvocationContext | None = None,
    ) -> TranscriptDocument:
        if global_offset_ms < 0:
            raise ValueError("global_offset_ms cannot be negative")
        invocation = context or InvocationContext(
            prompt_version="asr-transcription.v1",
            config_version=ASR_MERGE_POLICY_VERSION,
            timeout_seconds=120.0,
            max_output_tokens=4096,
        )
        output: list[GlobalTranscriptSegment] = []
        metadata = None
        detected_language = language
        for chunk in chunks:
            result = self._model.transcribe(
                AsrRequest(audio_ref=chunk.audio_ref, language=language, context=invocation)
            )
            metadata = result.metadata
            detected_language = result.parsed.language
            chunk_duration = chunk.end_ms - chunk.start_ms
            for segment in result.parsed.segments:
                relative_start = max(0, min(chunk_duration, round(segment.start_seconds * 1000)))
                relative_end = max(0, min(chunk_duration, round(segment.end_seconds * 1000)))
                text = segment.text.strip()
                if relative_end <= relative_start or not text:
                    continue
                output.append(
                    GlobalTranscriptSegment(
                        start_ms=global_offset_ms + chunk.start_ms + relative_start,
                        end_ms=global_offset_ms + chunk.start_ms + relative_end,
                        text=text,
                        source_chunk_id=chunk.chunk_id,
                    )
                )
        output.sort(key=lambda item: (item.start_ms, item.end_ms, item.text))
        return TranscriptDocument(
            language=detected_language,
            segments=output,
            model_provider=metadata.provider if metadata else None,
            model_name=metadata.model if metadata else None,
            model_revision=metadata.model_revision if metadata else None,
        )


def _component(value: str) -> str:
    normalized = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    if not normalized:
        raise ValueError("asset_id is invalid")
    return normalized[:80]
