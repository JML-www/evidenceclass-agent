"""Versioned, reproducible frame sampling on one global millisecond timeline."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, model_validator

from .errors import MediaToolExecutionError
from .probe import MediaProbe
from .tools import CommandRunner, SubprocessCommandRunner, resolve_media_tool, sanitized_stderr

SAMPLING_POLICY_VERSION = "frame-sampling.v1"
_PTS_TIME = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class SamplingPolicy(_StrictModel):
    version: str = SAMPLING_POLICY_VERSION
    mode: Literal["uniform", "scene_change"] = "uniform"
    sample_count: PositiveInt = 12
    scene_threshold: float = Field(default=0.35, gt=0.0, lt=1.0)
    max_scene_frames: PositiveInt = 30


class SampledFrame(_StrictModel):
    frame_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    local_timestamp_ms: NonNegativeInt
    global_timestamp_ms: NonNegativeInt
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    object_ref: str = Field(min_length=1)
    sampling_policy_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_timeline(self) -> SampledFrame:
        if self.global_timestamp_ms < self.local_timestamp_ms:
            raise ValueError("global timestamp cannot precede local timestamp")
        return self


class FrameSink(Protocol):
    def put(
        self,
        *,
        asset_id: str,
        camera_id: str,
        global_timestamp_ms: int,
        sha256: str,
        data: bytes,
    ) -> str: ...


class LocalFrameSink:
    """Development sink with deterministic names; production can provide an object-store sink."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        *,
        asset_id: str,
        camera_id: str,
        global_timestamp_ms: int,
        sha256: str,
        data: bytes,
    ) -> str:
        safe_asset = _safe_component(asset_id)
        safe_camera = _safe_component(camera_id)
        destination = (
            self.root / safe_asset / safe_camera / (f"{global_timestamp_ms:012d}_{sha256[:16]}.png")
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != data:
            raise MediaToolExecutionError(
                "deterministic frame object collided with different bytes"
            )
        if not destination.exists():
            destination.write_bytes(data)
        return destination.as_uri()


def _safe_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]", "_", value)
    if not normalized:
        raise ValueError("asset and camera identifiers need an ASCII-safe character")
    return normalized[:80]


def uniform_timestamps(duration_ms: int, sample_count: int) -> list[int]:
    """Return center-of-bin timestamps; integer arithmetic makes the plan reproducible."""

    if duration_ms <= 0 or sample_count <= 0:
        raise ValueError("duration and sample count must be positive")
    count = min(duration_ms, sample_count)
    return [
        min(duration_ms - 1, ((2 * index + 1) * duration_ms) // (2 * count))
        for index in range(count)
    ]


class ReproducibleFrameSampler:
    def __init__(
        self,
        *,
        sink: FrameSink,
        ffmpeg_path: str | Path | None = None,
        runner: CommandRunner | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._sink = sink
        self._ffmpeg = resolve_media_tool("ffmpeg", ffmpeg_path)
        self._runner = runner or SubprocessCommandRunner()
        self._timeout = timeout_seconds

    def sample(
        self,
        source: str | Path,
        *,
        probe: MediaProbe,
        asset_id: str,
        camera_id: str,
        global_offset_ms: int = 0,
        policy: SamplingPolicy | None = None,
    ) -> list[SampledFrame]:
        if global_offset_ms < 0:
            raise ValueError("global_offset_ms cannot be negative")
        selected = policy or SamplingPolicy()
        if selected.mode == "uniform":
            timestamps = uniform_timestamps(probe.duration_ms, selected.sample_count)
        else:
            timestamps = self._scene_timestamps(source, selected, probe.duration_ms)
        frames = [
            self._extract_one(
                source,
                timestamp_ms=timestamp,
                global_timestamp_ms=global_offset_ms + timestamp,
                asset_id=asset_id,
                camera_id=camera_id,
                policy_version=selected.version,
            )
            for timestamp in timestamps
        ]
        if [item.global_timestamp_ms for item in frames] != sorted(
            item.global_timestamp_ms for item in frames
        ):
            raise MediaToolExecutionError("sampled frame timeline is not ordered")
        return frames

    def _extract_one(
        self,
        source: str | Path,
        *,
        timestamp_ms: int,
        global_timestamp_ms: int,
        asset_id: str,
        camera_id: str,
        policy_version: str,
    ) -> SampledFrame:
        result = self._runner.run(
            (
                str(self._ffmpeg),
                "-nostdin",
                "-v",
                "error",
                "-ss",
                f"{timestamp_ms / 1000:.3f}",
                "-i",
                str(Path(source).resolve()),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-map_metadata",
                "-1",
                "-an",
                "-sn",
                "-dn",
                "-threads",
                "1",
                "-c:v",
                "png",
                "-f",
                "image2pipe",
                "-",
            ),
            timeout_seconds=self._timeout,
        )
        if result.returncode != 0 or not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
            raise MediaToolExecutionError(
                "FFmpeg did not produce a valid sampled PNG",
                details={"diagnostic": sanitized_stderr(result)},
            )
        digest = hashlib.sha256(result.stdout).hexdigest()
        object_ref = self._sink.put(
            asset_id=asset_id,
            camera_id=camera_id,
            global_timestamp_ms=global_timestamp_ms,
            sha256=digest,
            data=result.stdout,
        )
        frame_id = hashlib.sha256(
            f"{asset_id}|{camera_id}|{global_timestamp_ms}|{policy_version}|{digest}".encode()
        ).hexdigest()[:24]
        return SampledFrame(
            frame_id=f"frame_{frame_id}",
            asset_id=asset_id,
            camera_id=camera_id,
            local_timestamp_ms=timestamp_ms,
            global_timestamp_ms=global_timestamp_ms,
            sha256=digest,
            object_ref=object_ref,
            sampling_policy_version=policy_version,
        )

    def _scene_timestamps(
        self, source: str | Path, policy: SamplingPolicy, duration_ms: int
    ) -> list[int]:
        filter_value = f"select=gt(scene\\,{policy.scene_threshold}),showinfo"
        result = self._runner.run(
            (
                str(self._ffmpeg),
                "-nostdin",
                "-v",
                "info",
                "-i",
                str(Path(source).resolve()),
                "-vf",
                filter_value,
                "-an",
                "-f",
                "null",
                "-",
            ),
            timeout_seconds=self._timeout,
        )
        if result.returncode != 0:
            raise MediaToolExecutionError(
                "scene-change sampling failed",
                details={"diagnostic": sanitized_stderr(result)},
            )
        points = sorted(
            {
                min(duration_ms - 1, max(0, round(float(value) * 1000)))
                for value in _PTS_TIME.findall(result.stderr.decode("utf-8", errors="replace"))
            }
        )
        if not points:
            points = [uniform_timestamps(duration_ms, 1)[0]]
        return points[: policy.max_scene_frames]
