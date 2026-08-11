"""Safe ffprobe-based inspection before any expensive model call."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveFloat, PositiveInt

from .errors import (
    CorruptMediaError,
    MediaLimitExceededError,
    UnsafeMediaPathError,
    UnsupportedMediaError,
)
from .tools import (
    CommandRunner,
    SubprocessCommandRunner,
    resolve_media_tool,
    sanitized_stderr,
)

PROBE_POLICY_VERSION = "media-probe.v1"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class VideoStreamInfo(_StrictModel):
    codec: str = Field(min_length=1)
    width: PositiveInt
    height: PositiveInt
    fps: PositiveFloat
    rotation_degrees: int = 0


class AudioStreamInfo(_StrictModel):
    codec: str = Field(min_length=1)
    channels: PositiveInt
    sample_rate_hz: PositiveInt


class MediaProbe(_StrictModel):
    policy_version: str = PROBE_POLICY_VERSION
    source_name: str = Field(min_length=1)
    duration_ms: PositiveInt
    file_size_bytes: PositiveInt
    container: str = Field(min_length=1)
    video: VideoStreamInfo
    audio_streams: list[AudioStreamInfo] = Field(default_factory=list)
    stream_count: PositiveInt
    metadata_bytes: NonNegativeInt

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000


@dataclass(frozen=True)
class ProbePolicy:
    """MVP defaults intentionally cap inputs at ten minutes and common web codecs."""

    max_duration_seconds: float = 600.0
    max_file_bytes: int = 512 * 1024 * 1024
    max_width: int = 3840
    max_height: int = 2160
    max_fps: float = 120.0
    max_streams: int = 16
    max_metadata_bytes: int = 64 * 1024
    max_probe_json_bytes: int = 2 * 1024 * 1024
    supported_video_codecs: frozenset[str] = field(
        default_factory=lambda: frozenset({"h264", "hevc", "mpeg4", "vp8", "vp9", "av1"})
    )
    supported_audio_codecs: frozenset[str] = field(
        default_factory=lambda: frozenset({"aac", "mp3", "opus", "vorbis", "pcm_s16le"})
    )
    supported_extensions: frozenset[str] = field(
        default_factory=lambda: frozenset({".mp4", ".mov", ".mkv", ".webm"})
    )
    validate_decode: bool = True
    tool_timeout_seconds: float = 120.0


def _parse_fraction(value: str) -> float:
    try:
        fraction = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise CorruptMediaError("video frame rate is invalid") from exc
    fps = float(fraction)
    if fps <= 0:
        raise CorruptMediaError("video frame rate must be positive")
    return fps


def _rotation(stream: dict[str, Any]) -> int:
    tags = stream.get("tags") or {}
    if "rotate" in tags:
        try:
            return int(float(tags["rotate"])) % 360
        except (TypeError, ValueError):
            pass
    for item in stream.get("side_data_list") or []:
        if "rotation" in item:
            try:
                return int(round(float(item["rotation"]))) % 360
            except (TypeError, ValueError):
                continue
    return 0


def _metadata_size(payload: dict[str, Any]) -> int:
    tags: list[dict[str, Any]] = []
    if isinstance(payload.get("format", {}).get("tags"), dict):
        tags.append(payload["format"]["tags"])
    for stream in payload.get("streams") or []:
        if isinstance(stream.get("tags"), dict):
            tags.append(stream["tags"])
    return len(json.dumps(tags, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _safe_local_file(source: str | Path, policy: ProbePolicy, allowed_root: Path | None) -> Path:
    raw = str(source)
    if "\x00" in raw or "://" in raw:
        raise UnsafeMediaPathError("media source must be a local filesystem path")
    candidate = Path(source).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise UnsafeMediaPathError("media source does not exist or cannot be resolved") from exc
    if not resolved.is_file() or resolved.suffix.lower() not in policy.supported_extensions:
        raise UnsupportedMediaError("media extension or source type is not supported")
    if allowed_root is not None:
        root = allowed_root.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise UnsafeMediaPathError("media source is outside the authorized root") from exc
    return resolved


class SafeMediaProbe:
    def __init__(
        self,
        *,
        policy: ProbePolicy | None = None,
        ffprobe_path: str | Path | None = None,
        ffmpeg_path: str | Path | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.policy = policy or ProbePolicy()
        self._ffprobe = resolve_media_tool("ffprobe", ffprobe_path)
        self._ffmpeg = resolve_media_tool("ffmpeg", ffmpeg_path)
        self._runner = runner or SubprocessCommandRunner()

    def inspect(self, source: str | Path, *, allowed_root: Path | None = None) -> MediaProbe:
        path = _safe_local_file(source, self.policy, allowed_root)
        size = path.stat().st_size
        if size <= 0:
            raise CorruptMediaError("media file is empty")
        if size > self.policy.max_file_bytes:
            raise MediaLimitExceededError("media file exceeds the configured size limit")
        result = self._runner.run(
            (
                str(self._ffprobe),
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ),
            timeout_seconds=self.policy.tool_timeout_seconds,
        )
        if result.returncode != 0:
            raise CorruptMediaError(
                "ffprobe could not parse the media container",
                details={"diagnostic": sanitized_stderr(result)},
            )
        if len(result.stdout) > self.policy.max_probe_json_bytes:
            raise MediaLimitExceededError("ffprobe output exceeds the metadata safety limit")
        try:
            payload = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CorruptMediaError("ffprobe returned invalid JSON") from exc
        probe = self._validate_payload(path, size, payload)
        if self.policy.validate_decode:
            self._validate_decodable(path)
        return probe

    def _validate_payload(self, path: Path, size: int, payload: dict[str, Any]) -> MediaProbe:
        streams = payload.get("streams")
        if not isinstance(streams, list) or not streams:
            raise UnsupportedMediaError("media contains no decodable streams")
        if len(streams) > self.policy.max_streams:
            raise MediaLimitExceededError("media contains too many streams")
        video_streams = [item for item in streams if item.get("codec_type") == "video"]
        if not video_streams:
            raise UnsupportedMediaError("media does not contain a video stream")
        raw_video = video_streams[0]
        codec = str(raw_video.get("codec_name") or "")
        if codec not in self.policy.supported_video_codecs:
            raise UnsupportedMediaError(f"video codec is not supported: {codec or 'unknown'}")
        width = int(raw_video.get("width") or 0)
        height = int(raw_video.get("height") or 0)
        fps = _parse_fraction(str(raw_video.get("avg_frame_rate") or raw_video.get("r_frame_rate")))
        duration_value = payload.get("format", {}).get("duration") or raw_video.get("duration")
        try:
            duration = float(duration_value)
        except (TypeError, ValueError) as exc:
            raise CorruptMediaError("media duration is missing or invalid") from exc
        if duration <= 0:
            raise CorruptMediaError("media duration must be positive")
        if duration > self.policy.max_duration_seconds:
            raise MediaLimitExceededError("media duration exceeds the MVP limit")
        if width <= 0 or height <= 0:
            raise CorruptMediaError("video dimensions are missing")
        if width > self.policy.max_width or height > self.policy.max_height:
            raise MediaLimitExceededError("video dimensions exceed the configured limit")
        if fps > self.policy.max_fps:
            raise MediaLimitExceededError("video frame rate exceeds the configured limit")

        audio_streams: list[AudioStreamInfo] = []
        for item in streams:
            if item.get("codec_type") != "audio":
                continue
            audio_codec = str(item.get("codec_name") or "")
            if audio_codec not in self.policy.supported_audio_codecs:
                name = audio_codec or "unknown"
                raise UnsupportedMediaError(f"audio codec is not supported: {name}")
            try:
                audio_streams.append(
                    AudioStreamInfo(
                        codec=audio_codec,
                        channels=int(item.get("channels") or 0),
                        sample_rate_hz=int(item.get("sample_rate") or 0),
                    )
                )
            except (TypeError, ValueError) as exc:
                raise CorruptMediaError("audio stream metadata is invalid") from exc

        metadata_bytes = _metadata_size(payload)
        if metadata_bytes > self.policy.max_metadata_bytes:
            raise MediaLimitExceededError("media metadata exceeds the configured limit")
        container = str(payload.get("format", {}).get("format_name") or "unknown")
        return MediaProbe(
            source_name=path.name,
            duration_ms=max(1, round(duration * 1000)),
            file_size_bytes=size,
            container=container,
            video=VideoStreamInfo(
                codec=codec,
                width=width,
                height=height,
                fps=fps,
                rotation_degrees=_rotation(raw_video),
            ),
            audio_streams=audio_streams,
            stream_count=len(streams),
            metadata_bytes=metadata_bytes,
        )

    def _validate_decodable(self, path: Path) -> None:
        result = self._runner.run(
            (
                str(self._ffmpeg),
                "-nostdin",
                "-v",
                "error",
                "-xerror",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-f",
                "null",
                "-",
            ),
            timeout_seconds=self.policy.tool_timeout_seconds,
        )
        if result.returncode != 0:
            raise CorruptMediaError(
                "media streams failed decode validation",
                details={"diagnostic": sanitized_stderr(result)},
            )
