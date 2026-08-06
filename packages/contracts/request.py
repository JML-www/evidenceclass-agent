# packages/contracts/request.py
from datetime import timedelta

from pydantic import Field, PositiveFloat

from .base import BaseContract


class TimeWindowConfig(BaseContract):
    """全局分析时间窗口配置"""
    start_offset_sec: float = Field(ge=0.0)
    duration_sec: PositiveFloat
    step_sec: PositiveFloat = 1.0

    @property
    def duration_timedelta(self) -> timedelta:
        return timedelta(seconds=self.duration_sec)


class VisibleRegionRule(BaseContract):
    """画面区域可见性规则"""
    region_id: str
    min_area_ratio: float = Field(ge=0.0, le=1.0)
    enable_behavior_count: bool = True


class MetricSwitch(BaseContract):
    """指标开关控制"""
    enable_overlap_count: bool = True
    enable_talk_duration: bool = True
    enable_student_participation: bool = True


class AnalysisRequest(BaseContract):
    """顶层分析任务请求契约"""
    task_id: str
    course_tag: str
    is_image_mode: bool
    time_window: TimeWindowConfig
    regions: list[VisibleRegionRule]
    metrics: MetricSwitch
    shard_ids: list[str] | None = None