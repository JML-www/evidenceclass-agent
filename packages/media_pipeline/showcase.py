"""Pure global-timeline planning for short review windows."""

from __future__ import annotations

from typing import Any


def _parse_time(value: str) -> float:
    parts = [float(part) for part in value.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    raise ValueError(f"invalid time: {value}")


def build_windows(
    timestamps: list[str], clip_seconds: float, lead_seconds: float
) -> list[dict[str, Any]]:
    """Build numbered windows without losing their original timeline offsets."""
    if clip_seconds <= 0 or lead_seconds < 0:
        raise ValueError("clip duration must be positive and lead must be non-negative")
    windows = []
    for index, timestamp in enumerate(timestamps, start=1):
        reference = _parse_time(timestamp)
        windows.append(
            {
                "index": index,
                "referenceTime": timestamp,
                "referenceSeconds": reference,
                "globalStartSeconds": round(max(0.0, reference - lead_seconds), 3),
                "durationSeconds": round(clip_seconds, 3),
            }
        )
    return windows
