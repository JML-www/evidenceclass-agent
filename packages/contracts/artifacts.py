# packages/contracts/artifacts.py
from pydantic import Field, NonNegativeFloat, NonNegativeInt

from .base import BaseContract

# 移到顶部提前导入，解决E402
from .region import RegionObservation


class VideoShard(BaseContract):
    """视频分片元数据"""
    shard_id: str
    file_tag: str
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(ge=0.0)
    frame_count: NonNegativeInt


class MetricResult(BaseContract):
    """单条指标输出数值契约"""
    metric_key: str
    value: float
    lower_bound: NonNegativeFloat
    weight: float = Field(ge=0.0, le=1.0)


class EvidenceArtifact(BaseContract):
    """最终合并证据产物契约"""
    task_id: str
    shards: list[VideoShard]
    region_stats: list[RegionObservation]
    metrics: list[MetricResult]
    total_duration_min: NonNegativeFloat
    generated_at_sec: float


# 仅保留重建语句，删掉底部import
EvidenceArtifact.model_rebuild()