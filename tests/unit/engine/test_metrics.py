import json
from pathlib import Path
from packages.evidence_engine.builder import build_evidence_pack
from packages.evidence_engine.metrics import frame_metrics, aggregate_metric

# 1. test_metric_values_are_bounded_or_unknown
def test_metric_values_are_bounded_or_unknown():
    """所有指标0~100或null未知兜底"""
    payload = json.loads(Path("fixtures/image-demo.json").read_text(encoding="utf-8"))
    frame = payload["frames"][0]
    vals = frame_metrics(frame, payload["courseInfo"]["studentCount"], mode="image")
    for v in vals.values():
        assert v is None or 0 <= v <= 100

# 2. test_overlapping_behavior_counts_use_a_lower_bound
def test_overlapping_behavior_counts_use_a_lower_bound():
    """重叠行为按人数下限计算占比"""
    payload = json.loads(Path("fixtures/image-demo.json").read_text(encoding="utf-8"))
    frame = payload["frames"][0]
    res = frame_metrics(frame, student_count=18, mode="image")
    assert res["participation"] == round(5 / 18 * 100, 1)
    assert res["interaction"] == round(2 / 18 * 100, 1)

# 3. test_model_confidence_is_not_an_aggregation_weight
def test_model_confidence_is_not_an_aggregation_weight():
    """模型置信度不参与指标加权平均"""
    frame_list = [
        {"metrics": {"focus": 100.0}, "confidence": 0.99, "observationDurationSeconds": 1.0},
        {"metrics": {"focus": 0.0}, "confidence": 0.01, "observationDurationSeconds": 1.0},
    ]
    agg = aggregate_metric(frame_list, target_key="focus")
    assert agg == 50.0

# 4. test_sourced_user_rubric_controls_weights_and_target
def test_sourced_user_rubric_controls_weights_and_target():
    """自定义评分量表覆盖指标权重与阈值"""
    import tempfile
    payload = json.loads(Path("fixtures/video-demo.json").read_text(encoding="utf-8"))
    payload["evaluationRubric"] = {
        "name": "测试量表",
        "version": "1.0",
        "source": "tests/fixture-rubric",
        "weights": {"focus": 1, "participation": 0, "interaction": 0, "teacherGuidance": 0, "teachingRhythm": 0},
        "targets": {"interaction": {"min": 20}, "podiumShare": {"max": 60}},
    }
    with tempfile.TemporaryDirectory() as tmp:
        rub_file = Path(tmp) / "rubric.json"
        rub_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        out = Path(tmp) / "pack"
        build_evidence_pack(payload, out)
        pkg = json.loads((out / "analysis_data.json").read_text(encoding="utf-8"))
        metrics = pkg["metrics"]
        assert metrics["summary"]["overall"] == metrics["summary"]["focus"]
        assert metrics["summary"]["scoring"]["source"] == "tests/fixture-rubric"
        alert_metrics = {i["metric"] for i in metrics["alerts"]}
        assert "interaction" in alert_metrics
        assert "按用户量表调整课堂移动" in {i["title"] for i in metrics["actions"]}