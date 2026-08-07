"""Versioned output and storage manifests."""

from pydantic import Field, NonNegativeFloat, NonNegativeInt, model_validator

from .base import BaseContract
from .region import RegionObservation


class VideoShard(BaseContract):
    """Media shard metadata; timestamps are seconds from the original media."""

    shard_id: str = Field(min_length=1, description="Stable shard identifier.")
    file_tag: str = Field(min_length=1, description="Synthetic or object-store file tag.")
    start_sec: NonNegativeFloat = Field(description="Shard start in seconds.")
    end_sec: NonNegativeFloat = Field(description="Shard end in seconds.")
    frame_count: NonNegativeInt = Field(description="Number of sampled frames in the shard.")

    @model_validator(mode="after")
    def validate_time_order(self) -> "VideoShard":
        if self.end_sec < self.start_sec:
            raise ValueError("end_sec must be greater than or equal to start_sec")
        return self


class MetricResult(BaseContract):
    """A deterministic metric value and its conservative lower bound."""

    metric_key: str = Field(min_length=1, description="Stable metric name.")
    value: float = Field(description="Metric value in the metric's documented unit.")
    lower_bound: NonNegativeFloat = Field(description="Conservative lower bound in the same unit.")
    weight: float = Field(ge=0.0, le=1.0, description="Rubric weight normalized to 0..1.")

    @model_validator(mode="after")
    def validate_lower_bound(self) -> "MetricResult":
        if self.lower_bound > self.value:
            raise ValueError("lower_bound cannot exceed value")
        return self


class EvidenceArtifact(BaseContract):
    """Legacy-compatible deterministic artifact envelope."""

    task_id: str = Field(min_length=1, description="Owning analysis task identifier.")
    shards: list[VideoShard] = Field(description="Input shard metadata.")
    region_stats: list[RegionObservation] = Field(description="Aggregated region observations.")
    metrics: list[MetricResult] = Field(description="Deterministic metric outputs.")
    total_duration_min: NonNegativeFloat = Field(description="Total duration in minutes.")
    generated_at_sec: NonNegativeFloat = Field(description="Generation timestamp in seconds.")


EvidenceArtifact.model_rebuild()
