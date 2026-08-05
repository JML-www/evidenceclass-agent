"""Pure upload-planning logic; media probing and encoding are intentionally deferred."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VideoInfo:
    filename: str
    total_seconds: float
    width: int
    height: int
    fps: float
    file_bytes: int


def build_plan(
    info: VideoInfo,
    limit_mib: float,
    strategy: str,
    minimum_total_kbps: int,
    target_total_kbps: int,
    safety_factor: float = 0.90,
    audio_kbps: int = 64,
) -> dict[str, Any]:
    """Choose one compressed file or ordered parts under the configured byte budget."""
    if info.total_seconds <= 0 or limit_mib <= 0:
        raise ValueError("video duration and upload limit must be positive")
    if strategy not in {"auto", "compress", "split"}:
        raise ValueError("strategy must be auto, compress, or split")

    limit_bytes = int(limit_mib * 1024 * 1024)
    safe_bytes = int(limit_bytes * safety_factor)
    full_total_kbps = math.floor(safe_bytes * 8 / info.total_seconds / 1000)
    use_single = strategy == "compress" or (
        strategy == "auto" and full_total_kbps >= minimum_total_kbps
    )
    if strategy == "split":
        use_single = False

    if use_single:
        total_kbps = max(full_total_kbps, 96)
        segments = [{"index": 1, "startSeconds": 0.0, "durationSeconds": info.total_seconds}]
    else:
        total_kbps = max(target_total_kbps, minimum_total_kbps)
        part_seconds = max(60, math.floor(safe_bytes * 8 / (total_kbps * 1000)))
        segments = []
        for index in range(math.ceil(info.total_seconds / part_seconds)):
            start = index * part_seconds
            segments.append(
                {
                    "index": index + 1,
                    "startSeconds": round(start, 3),
                    "durationSeconds": round(min(part_seconds, info.total_seconds - start), 3),
                }
            )

    return {
        "strategy": "single_compress" if use_single else "ordered_split",
        "limitBytes": limit_bytes,
        "fullFileTargetKbps": full_total_kbps,
        "totalTargetKbps": total_kbps,
        "videoTargetKbps": max(total_kbps - audio_kbps - 16, 64),
        "audioTargetKbps": audio_kbps,
        "segments": segments,
    }
