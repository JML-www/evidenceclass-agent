# tests/unit/test_contracts/test_contract_validation.py
import pytest
from pydantic import ValidationError

from packages.contracts import (
    AnalysisRequest,
    BoundingBox,
    FrameObservation,
    MetricResult,
    MetricSwitch,
    RegionObservation,
    TimeWindowConfig,
    VideoShard,
    VisibleRegionRule,
)


def test_time_window_negative_duration_fails():
    """时长为负数，契约校验抛出异常"""
    with pytest.raises(ValidationError):
        TimeWindowConfig(start_offset_sec=0, duration_sec=-5.0)

def test_bounding_box_coords_out_of_range():
    """坐标超过0~1归一化范围拦截"""
    with pytest.raises(ValidationError):
        BoundingBox(x1=-0.1, y1=0, x2=1.2, y2=1)

def test_frame_contains_extra_field_forbidden():
    """多余未定义字段直接报错（extra="forbid"）"""
    raw_data = {
        "frame_time_sec": 10.0,
        "region_id": "reg_01",
        "student_id": "stu_001",
        "behavior": "listen",
        "confidence": 0.85,
        "box": {"x1": 0, "y1": 0, "x2": 1, "y2": 1},
        "random_extra_field": 12345
    }
    with pytest.raises(ValidationError):
        FrameObservation(**raw_data)

def test_video_shard_end_less_than_start():
    """分片结束时间早于开始时间非法"""
    with pytest.raises(ValidationError):
        VideoShard(
            shard_id="shard_1",
            file_tag="video_demo",
            start_sec=60.0,
            end_sec=30.0,
            frame_count=200
        )

def test_region_overlap_rate_over_one():
    """参与率大于100%非法"""
    with pytest.raises(ValidationError):
        RegionObservation(
            region_id="r1",
            total_student_count=10,
            active_count=5,
            total_talk_minutes=12.5,
            overlap_participation_rate=1.3
        )

def test_metric_weight_exceed_one():
    """指标权重超过1拦截"""
    with pytest.raises(ValidationError):
        MetricResult(metric_key="talk_ratio", value=0.6, lower_bound=0, weight=1.2)

def test_analysis_request_missing_required_field():
    """缺失必填task_id触发校验失败"""
    raw_req = {
        "course_tag": "math_demo",
        "is_image_mode": False,
        "time_window": TimeWindowConfig(start_offset_sec=0, duration_sec=600),
        "regions": [VisibleRegionRule(region_id="r1")],
        "metrics": MetricSwitch()
    }
    with pytest.raises(ValidationError):
        AnalysisRequest(**raw_req)