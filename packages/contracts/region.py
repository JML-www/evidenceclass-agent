# packages/contracts/region.py
from pydantic import Field, NonNegativeFloat, NonNegativeInt

from .base import BaseContract


class RegionObservation(BaseContract):
    """单区域聚合统计结果"""
    region_id: str
    total_student_count: NonNegativeInt
    active_count: NonNegativeInt
    total_talk_minutes: NonNegativeFloat
    overlap_participation_rate: float = Field(ge=0.0, le=1.0)