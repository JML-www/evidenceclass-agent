from packages.media_pipeline.video_prepare import VideoInfo, build_plan

# 1. test_video_mode_has_timeline_and_behavior_share
def test_video_mode_has_timeline_and_behavior_share():
    """视频模式生成完整时间轴与行为分布图表"""
    import json
    import tempfile
    from pathlib import Path
    from packages.evidence_engine.builder import build_evidence_pack
    payload = json.loads(Path("fixtures/video-demo.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        res = build_evidence_pack(payload, out)
        pkg = json.loads((out / "analysis_data.json").read_text(encoding="utf-8"))
        metrics = pkg["metrics"]
        assert res["analysisMode"] == "video"
        assert metrics["behaviorDistribution"]["available"] is True
        assert metrics["positionDistribution"]["available"] is True
        assert metrics["positionDistribution"]["items"][0]["percent"] >= 60
        action_titles = {item["title"] for item in metrics["actions"]}
        assert "核对教师位置与指导覆盖" in action_titles
        assert len(metrics["frames"]) == 7
        dashboard = (out / "dashboard.html").read_text(encoding="utf-8")
        assert "behavior-pie" in dashboard

# 2. test_large_video_plan_switches_to_ordered_parts
def test_large_video_plan_switches_to_ordered_parts():
    """超大视频自动有序分片策略"""
    vid_info = VideoInfo(
        filename="demo.mp4",
        total_seconds=2765.0,
        width=1920,
        height=1080,
        fps=25.0,
        file_bytes=3_408_000_000
    )
    plan = build_plan(vid, target_sec=49.0, mode="auto", min_seg=500, max_seg=760)
    assert plan["strategy"] == "ordered_split"
    assert plan["fullFileTargetKbps"] == 133
    assert len(plan["segments"]) == 6
    assert all(s["durationSeconds"] <= 486 for s in plan["segments"])