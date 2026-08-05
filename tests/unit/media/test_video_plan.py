import json
from pathlib import Path

from packages.evidence_engine.metrics import percentage_distribution
from packages.evidence_engine.validation import mode_capabilities
from packages.media_pipeline.video_plan import VideoInfo, build_plan

ROOT = Path(__file__).resolve().parents[3]
VIDEO_FIXTURE = ROOT / "fixtures" / "structured" / "video-demo.json"


def test_video_mode_enables_timeline_and_duration_distributions():
    payload = json.loads(VIDEO_FIXTURE.read_text(encoding="utf-8"))

    capabilities = mode_capabilities(payload)
    position_share = percentage_distribution(payload["teacherPositionDurations"])

    assert capabilities == {
        "wholeLessonMetrics": True,
        "timeline": True,
        "behaviorDistribution": True,
        "positionDistribution": True,
    }
    assert len(payload["frames"]) == 7
    assert position_share["podium"] >= 60


def test_large_video_is_split_into_ordered_upload_parts():
    info = VideoInfo(
        filename="video-sample-001.mp4",
        total_seconds=2765.0,
        width=1920,
        height=1080,
        fps=25.0,
        file_bytes=3_408_000_000,
    )

    plan = build_plan(
        info,
        limit_mib=49.0,
        strategy="auto",
        minimum_total_kbps=500,
        target_total_kbps=760,
    )

    assert plan["strategy"] == "ordered_split"
    assert plan["fullFileTargetKbps"] == 133
    assert len(plan["segments"]) == 6
    assert [segment["index"] for segment in plan["segments"]] == [1, 2, 3, 4, 5, 6]
    assert all(segment["durationSeconds"] <= 486 for segment in plan["segments"])
