"""Idempotent long-media segment manifests and global-timeline observation merge."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, model_validator

from .errors import MediaManifestError
from .vision import ObservableLabel

SEGMENT_MANIFEST_VERSION = "media-segments.v1"
SEGMENT_MERGE_VERSION = "segment-observation-merge.v1"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class SegmentSpec(_StrictModel):
    segment_id: str = Field(min_length=1)
    index: PositiveInt
    global_offset_ms: NonNegativeInt
    duration_ms: PositiveInt
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SegmentManifest(_StrictModel):
    version: str = SEGMENT_MANIFEST_VERSION
    asset_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    total_duration_ms: PositiveInt
    segments: list[SegmentSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contiguous_global_timeline(self) -> SegmentManifest:
        ordered = sorted(self.segments, key=lambda item: item.index)
        if [item.index for item in ordered] != list(range(1, len(ordered) + 1)):
            raise ValueError("segment indexes must be contiguous from one")
        if len({item.segment_id for item in ordered}) != len(ordered):
            raise ValueError("segment_id values must be unique")
        expected_offset = 0
        for item in ordered:
            if item.global_offset_ms != expected_offset:
                raise ValueError("segment offsets must form a gap-free global timeline")
            expected_offset += item.duration_ms
        if expected_offset != self.total_duration_ms:
            raise ValueError("segment durations must equal total_duration_ms")
        return self


class LocalEvidenceSpan(_StrictModel):
    evidence_id: str = Field(min_length=1)
    fact: str = Field(min_length=1)
    local_start_ms: NonNegativeInt
    local_end_ms: NonNegativeInt

    @model_validator(mode="after")
    def validate_time_order(self) -> LocalEvidenceSpan:
        if self.local_end_ms < self.local_start_ms:
            raise ValueError("local evidence end cannot precede start")
        return self


class SegmentObservation(_StrictModel):
    segment_id: str = Field(min_length=1)
    index: PositiveInt
    label_counts: dict[ObservableLabel, NonNegativeInt] = Field(default_factory=dict)
    duration_metrics_ms: dict[str, NonNegativeInt] = Field(default_factory=dict)
    weighted_metrics: dict[str, float] = Field(default_factory=dict)
    evidence: list[LocalEvidenceSpan] = Field(default_factory=list)


class GlobalEvidenceSpan(_StrictModel):
    evidence_id: str = Field(min_length=1)
    fact: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    global_start_ms: NonNegativeInt
    global_end_ms: NonNegativeInt


class MergedSegmentObservation(_StrictModel):
    merge_version: str = SEGMENT_MERGE_VERSION
    merge_id: str = Field(min_length=1)
    ordered_segment_ids: list[str]
    duplicate_inputs_ignored: NonNegativeInt
    label_counts: dict[str, NonNegativeInt]
    duration_metrics_ms: dict[str, NonNegativeInt]
    weighted_metrics: dict[str, float]
    evidence: list[GlobalEvidenceSpan]


def merge_segment_observations(
    manifest: SegmentManifest, observations: list[SegmentObservation]
) -> MergedSegmentObservation:
    """Sort, idempotently de-duplicate, require completeness, and globalize evidence."""

    specs = {item.segment_id: item for item in manifest.segments}
    unique: dict[str, SegmentObservation] = {}
    fingerprints: dict[str, str] = {}
    duplicate_count = 0
    for item in observations:
        spec = specs.get(item.segment_id)
        if spec is None or item.index != spec.index:
            raise MediaManifestError("observation does not match the segment manifest")
        fingerprint = hashlib.sha256(
            item.model_dump_json(exclude_none=False).encode("utf-8")
        ).hexdigest()
        if item.segment_id in unique:
            if fingerprints[item.segment_id] != fingerprint:
                raise MediaManifestError("conflicting duplicate segment observation")
            duplicate_count += 1
            continue
        unique[item.segment_id] = item
        fingerprints[item.segment_id] = fingerprint
    missing = [item.segment_id for item in manifest.segments if item.segment_id not in unique]
    if missing:
        raise MediaManifestError(
            "segment observations are incomplete",
            details={"missing_segment_ids": missing},
        )

    ordered_specs = sorted(manifest.segments, key=lambda item: item.index)
    label_counts: dict[str, int] = {}
    duration_metrics: dict[str, int] = {}
    weighted_numerators: dict[str, float] = {}
    weighted_denominators: dict[str, int] = {}
    evidence: list[GlobalEvidenceSpan] = []
    for spec in ordered_specs:
        item = unique[spec.segment_id]
        for key, value in item.label_counts.items():
            label_counts[key] = label_counts.get(key, 0) + int(value)
        for key, value in item.duration_metrics_ms.items():
            duration_metrics[key] = duration_metrics.get(key, 0) + int(value)
        for key, value in item.weighted_metrics.items():
            weighted_numerators[key] = weighted_numerators.get(key, 0.0) + (
                value * spec.duration_ms
            )
            weighted_denominators[key] = weighted_denominators.get(key, 0) + spec.duration_ms
        for span in item.evidence:
            if span.local_end_ms > spec.duration_ms:
                raise MediaManifestError("local evidence exceeds its segment duration")
            evidence.append(
                GlobalEvidenceSpan(
                    evidence_id=span.evidence_id,
                    fact=span.fact,
                    segment_id=spec.segment_id,
                    global_start_ms=spec.global_offset_ms + span.local_start_ms,
                    global_end_ms=spec.global_offset_ms + span.local_end_ms,
                )
            )
    weighted = {
        key: weighted_numerators[key] / weighted_denominators[key]
        for key in sorted(weighted_numerators)
    }
    merge_material = {
        "manifest": manifest.model_dump(mode="json"),
        "observations": [fingerprints[item.segment_id] for item in ordered_specs],
        "merge_version": SEGMENT_MERGE_VERSION,
    }
    merge_id = hashlib.sha256(
        json.dumps(merge_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return MergedSegmentObservation(
        merge_id=f"merge_{merge_id[:24]}",
        ordered_segment_ids=[item.segment_id for item in ordered_specs],
        duplicate_inputs_ignored=duplicate_count,
        label_counts=label_counts,
        duration_metrics_ms=duration_metrics,
        weighted_metrics=weighted,
        evidence=sorted(evidence, key=lambda item: (item.global_start_ms, item.evidence_id)),
    )
