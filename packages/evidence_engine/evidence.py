"""Deterministic evidence construction with stable, collision-checked IDs."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from packages.contracts import EvidenceItem


def time_to_seconds(value: Any) -> float | None:
    """Convert ``HH:MM:SS`` or a numeric offset to seconds; labels remain untimed."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("time must be seconds or HH:MM:SS")
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError("time cannot be negative")
        return float(value)
    if not isinstance(value, str) or value.count(":") != 2:
        return None
    try:
        hours, minutes, seconds = (float(part) for part in value.split(":"))
    except ValueError as exc:
        raise ValueError("time must be seconds or HH:MM:SS") from exc
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError("time must be a valid non-negative HH:MM:SS value")
    return hours * 3600 + minutes * 60 + seconds


def stable_evidence_id(
    *, source_ref: str, ordinal: int, fact: str, timestamp_sec: float | None
) -> str:
    """Derive an ID from semantic provenance, never from a clock or random value."""
    identity = json.dumps(
        {
            "fact": fact,
            "ordinal": ordinal,
            "source_ref": source_ref,
            "timestamp_sec": timestamp_sec,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"E-{hashlib.sha256(identity).hexdigest()[:16]}"


def build_evidence(payload: dict[str, Any]) -> list[EvidenceItem]:
    """Build contract-validated evidence from observable frame facts."""
    mode = payload["analysisMode"]
    items: list[EvidenceItem] = []
    seen: set[str] = set()
    for frame_index, frame in enumerate(payload["frames"]):
        source_ref = str(frame.get("frame_id") or f"frame-{frame_index + 1}")
        timestamp = time_to_seconds(frame.get("time"))
        limitations = [str(value) for value in frame.get("limitations", [])]
        for fact_index, raw_fact in enumerate(frame.get("evidence", [])):
            fact = str(raw_fact).strip()
            if not fact:
                continue
            ordinal = frame_index * 1_000_000 + fact_index
            evidence_id = stable_evidence_id(
                source_ref=source_ref,
                ordinal=ordinal,
                fact=fact,
                timestamp_sec=timestamp,
            )
            if evidence_id in seen:
                raise ValueError("evidence ID collision detected")
            seen.add(evidence_id)
            items.append(
                EvidenceItem(
                    evidence_id=evidence_id,
                    source_type=mode,
                    source_ref=source_ref,
                    fact=fact,
                    timestamp_start_sec=timestamp,
                    limitations=limitations,
                    confidence=(
                        float(frame["confidence"]) if frame.get("confidence") is not None else None
                    ),
                )
            )
    return items
