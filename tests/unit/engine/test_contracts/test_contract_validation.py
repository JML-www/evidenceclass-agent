from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from packages.contracts import (
    AnalysisRequest,
    AnalysisResult,
    ArtifactManifest,
    BoundingBox,
    EvaluationRubric,
    EvidenceItem,
    FrameObservation,
    MetricResult,
    MetricSwitch,
    OcrBlock,
    RegionObservation,
    RubricTarget,
    TimeWindowConfig,
    TranscriptSegment,
    VideoShard,
    VisibleRegionRule,
)

REQUIRED_CONTRACTS = (
    AnalysisRequest,
    FrameObservation,
    TranscriptSegment,
    OcrBlock,
    RegionObservation,
    EvaluationRubric,
    EvidenceItem,
    AnalysisResult,
    ArtifactManifest,
)


def test_time_window_negative_duration_fails():
    with pytest.raises(ValidationError):
        TimeWindowConfig(start_offset_sec=0.0, duration_sec=-5.0)

def test_bounding_box_coords_out_of_range():
    with pytest.raises(ValidationError):
        BoundingBox(x1=-0.1, y1=0, x2=1.2, y2=1)

def test_frame_contains_extra_field_forbidden():
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
    with pytest.raises(ValidationError):
        VideoShard(
            shard_id="shard_1",
            file_tag="video_demo",
            start_sec=60.0,
            end_sec=30.0,
            frame_count=200
        )

def test_region_overlap_rate_over_one():
    with pytest.raises(ValidationError):
        RegionObservation(
            region_id="r1",
            total_student_count=10,
            active_count=5,
            total_talk_minutes=12.5,
            overlap_participation_rate=1.3
        )

def test_metric_weight_exceed_one():
    with pytest.raises(ValidationError):
        MetricResult(metric_key="talk_ratio", value=0.6, lower_bound=0, weight=1.2)

def test_analysis_request_missing_required_field():
    raw_req = {
        "course_tag": "math_demo",
        "is_image_mode": False,
        "time_window": TimeWindowConfig(start_offset_sec=0, duration_sec=600),
        "regions": [VisibleRegionRule(region_id="r1")],
        "metrics": MetricSwitch()
    }
    with pytest.raises(ValidationError):
        AnalysisRequest(**raw_req)


def test_invisible_region_cannot_contain_numeric_observations():
    with pytest.raises(ValidationError, match="total_student_count") as exc_info:
        RegionObservation(
            region_id="back",
            visibility="not_visible",
            total_student_count=1,
        )
    assert exc_info.value.errors()[0]["loc"] == ("total_student_count",)


def test_behavior_count_cannot_exceed_visible_students():
    with pytest.raises(ValidationError, match="visible_student_count") as exc_info:
        RegionObservation(
            region_id="front",
            visible_student_count=3,
            behavior_count=4,
        )
    assert exc_info.value.errors()[0]["loc"] == ("behavior_count",)


def test_image_request_cannot_include_lesson_duration_or_shards():
    with pytest.raises(ValidationError, match="lesson_duration_sec") as exc_info:
        AnalysisRequest(
            task_id="task-1",
            course_tag="math",
            is_image_mode=True,
            time_window=TimeWindowConfig(start_offset_sec=0.0, duration_sec=1.0),
            regions=[VisibleRegionRule(region_id="front")],
            metrics=MetricSwitch(),
            lesson_duration_sec=600.0,
        )
    assert exc_info.value.errors()[0]["loc"] == ("lesson_duration_sec",)


def test_image_result_cannot_include_lesson_duration():
    with pytest.raises(ValidationError, match="lesson_duration_sec") as exc_info:
        AnalysisResult(
            task_id="task-1",
            analysis_mode="image",
            lesson_duration_sec=600.0,
        )
    assert exc_info.value.errors()[0]["loc"] == ("lesson_duration_sec",)


def test_image_result_cannot_include_transcript():
    transcript = TranscriptSegment(start_sec=0.0, end_sec=1.0, text="hello")
    with pytest.raises(ValidationError, match="transcript_segments") as exc_info:
        AnalysisResult(
            task_id="task-1",
            analysis_mode="image",
            transcript_segments=[transcript],
        )
    assert exc_info.value.errors()[0]["loc"] == ("transcript_segments",)


def test_teacher_ratio_requires_speaker_diarization():
    with pytest.raises(ValidationError, match="speaker_diarization_available") as exc_info:
        AnalysisResult(
            task_id="task-1",
            analysis_mode="video",
            teacher_speaking_ratio=0.4,
        )
    assert exc_info.value.errors()[0]["loc"] == ("teacher_speaking_ratio",)


def test_rubric_without_source_keeps_overall_unknown():
    with pytest.raises(ValidationError, match="overall") as exc_info:
        EvaluationRubric(name="local", version="1", overall=72.0)
    assert exc_info.value.errors()[0]["loc"] == ("overall",)


def test_contracts_expose_version_and_reject_wrong_version():
    request = AnalysisRequest(
        task_id="task-1",
        course_tag="math",
        is_image_mode=True,
        time_window=TimeWindowConfig(start_offset_sec=0.0, duration_sec=1.0),
        regions=[VisibleRegionRule(region_id="front")],
        metrics=MetricSwitch(),
    )
    assert request.schema_version == "contracts.v0.1"
    with pytest.raises(ValidationError, match="schema_version"):
        AnalysisRequest(
            schema_version="contracts.v0.2",
            task_id="task-1",
            course_tag="math",
            is_image_mode=True,
            time_window=TimeWindowConfig(start_offset_sec=0.0, duration_sec=1.0),
            regions=[VisibleRegionRule(region_id="front")],
            metrics=MetricSwitch(),
        )


def test_required_contract_fields_have_json_schema_descriptions():
    for contract in REQUIRED_CONTRACTS:
        properties = contract.model_json_schema()["properties"]
        assert properties["schema_version"]["default"] == "contracts.v0.1"
        assert all(property_schema.get("description") for property_schema in properties.values())


def test_valid_video_contract_graph_round_trips():
    frame = FrameObservation(
        frame_time_sec=2.0,
        region_id="front",
        student_id="anonymous-1",
        behavior="listen",
        confidence=0.9,
        box=BoundingBox(x1=0.1, y1=0.1, x2=0.2, y2=0.3),
        numeric_metrics={"focus": 90.0},
    )
    transcript = TranscriptSegment(
        start_sec=1.0,
        end_sec=3.0,
        text="Synthetic teacher speech",
        speaker_id="speaker-1",
        speaker_role="teacher",
    )
    rubric = EvaluationRubric(
        name="Synthetic rubric",
        version="1",
        source="fixtures/rubric-v1",
        weights={"focus": 1.0},
        targets={"focus": RubricTarget(minimum=60.0)},
        overall=90.0,
    )
    result = AnalysisResult(
        task_id="task-1",
        analysis_mode="video",
        observations=[frame],
        transcript_segments=[transcript],
        ocr_blocks=[OcrBlock(text="Synthetic slide", frame_time_sec=2.0)],
        region_observations=[
            RegionObservation(
                region_id="front",
                visible_student_count=3,
                behavior_counts={"listen": 2},
            )
        ],
        evidence=[
            EvidenceItem(
                evidence_id="ev-1",
                source_type="video",
                source_ref="frame-1",
                fact="Two visible students are listening.",
                timestamp_start_sec=2.0,
            )
        ],
        rubric=rubric,
        lesson_duration_sec=600.0,
        observed_duration_sec=10.0,
        speaker_diarization_available=True,
        teacher_speaking_ratio=0.4,
    )
    assert AnalysisResult.model_validate(result.model_dump()) == result
    manifest = ArtifactManifest(
        artifact_id="artifact-1",
        task_id="task-1",
        kind="analysis_result",
        object_key="results/task-1.json",
        sha256="a" * 64,
        version="1",
        created_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
    )
    assert manifest.schema_version == "contracts.v0.1"


def test_evidence_and_artifact_provenance_fields_are_typed():
    item = EvidenceItem(
        evidence_id="ev-1",
        source_type="video",
        source_ref="video_001",
        fact="Synthetic observation",
        timestamp_start_sec=2.0,
        timestamp_end_sec=3.0,
    )
    assert item.timestamp_end_sec == 3.0
    with pytest.raises(ValidationError):
        ArtifactManifest(
            artifact_id="a-1",
            task_id="task-1",
            kind="report",
            object_key="reports/task-1.json",
            sha256="not-a-sha",
            version="1",
            created_at="2026-08-07T00:00:00Z",
        )


def test_transcript_and_ocr_provenance_are_required():
    with pytest.raises(ValidationError):
        TranscriptSegment(start_sec=2.0, end_sec=1.0, text="bad")
    with pytest.raises(ValidationError, match="page_number or frame_time_sec"):
        OcrBlock(text="text")
    assert RubricTarget(minimum=0.0, maximum=1.0).maximum == 1.0
