# packages/contracts/frame.py
from typing import Literal

from pydantic import Field

from .base import BaseContract

BehaviorType = Literal["listen", "speak", "write", "interact", "idle"]


class BoundingBox(BaseContract):
    """画面坐标框"""
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)


class FrameObservation(BaseContract):
    """单帧识别观测结果"""
    frame_time_sec: float = Field(ge=0.0)
    region_id: str
    student_id: str
    behavior: BehaviorType
    confidence: float = Field(ge=0.0, le=1.0)
    box: BoundingBox