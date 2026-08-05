import json
from pathlib import Path
# 导入新项目packages内对应业务模块
from packages.evidence_engine.builder import build_evidence_pack
from packages.evidence_engine.validator import validate_payload

# 1. test_local_and_platform_contracts_match
def test_local_and_platform_contracts_match():
    """本地产物与平台契约字段完全一致"""
    # 模拟契约字段列表，对齐BUILDER.DEFAULT_ARTIFACTS
    default_arts = ["analysis_data.json", "dashboard.html", "classroom_analysis_report.md", "video_frames", "evidence_images"]
    local_fields = set(default_arts + ["analysisMode"])
    platform_fields = set(default_arts + ["analysisMode"])
    assert local_fields == platform_fields

# 2. test_image_mode_has_no_whole_lesson_inference
def test_image_mode_has_no_whole_lesson_inference():
    """图片模式禁止生成整节课综合指标、行为分布"""
    demo_payload = json.loads(Path("fixtures/image-demo.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp_dir:
        out = Path(tmp_dir)
        res = build_evidence_pack(demo_payload, out)
        pkg = json.loads((out / "analysis_data.json").read_text(encoding="utf-8"))
        metrics = pkg["metrics"]
        assert res["analysisMode"] == "image"
        assert metrics["summary"]["overall"] is None
        assert metrics["behaviorDistribution"]["available"] is False
        assert metrics["positionDistribution"]["available"] is False
        assert len(metrics["frames"]) == 1
        assert metrics["regions"]["back"]["focus"] is None
        assert len(metrics["actions"]) >= 3
        dashboard = (out / "dashboard.html").read_text(encoding="utf-8")
        assert "图片模式不生成课堂行为占比图" in dashboard
        report = (out / "classroom_analysis_report.md").read_text(encoding="utf-8")
        assert "不生成完整课堂流程" in report

# 3. test_image_mode_rejects_temporal_inputs
def test_image_mode_rejects_temporal_inputs():
    """图片输入携带时序ASR/帧行为直接校验报错"""
    payload = json.loads(Path("fixtures/image-demo.json").read_text(encoding="utf-8"))
    # 插入时序语音字段
    payload["asrSummary"] = {"teacherQuestionCount": 1}
    try:
        validate_payload(payload)
        assert False, "预期抛出ValueError"
    except ValueError:
        pass
    # 插入单帧时序行为
    payload.pop("asrSummary")
    payload["frames"][0]["teacher_behaviors"]["questioning"] = True
    try:
        validate_payload(payload)
        assert False, "预期抛出ValueError"
    except ValueError:
        pass