import json
from pathlib import Path

from packages.evidence_engine.metrics import aggregate_metric, evaluate_rubric, frame_metrics

ROOT = Path(__file__).resolve().parents[3]
IMAGE_FIXTURE = ROOT / "fixtures" / "structured" / "image-demo.json"


def _image_payload() -> dict:
    return json.loads(IMAGE_FIXTURE.read_text(encoding="utf-8"))


def test_frame_metrics_are_bounded_or_unknown():
    payload = _image_payload()

    values = frame_metrics(
        payload["frames"][0], payload["courseInfo"]["studentCount"], mode="image"
    )

    assert all(value is None or 0 <= value <= 100 for value in values.values())


def test_overlapping_behaviors_use_visible_student_lower_bounds():
    payload = _image_payload()

    values = frame_metrics(payload["frames"][0], fallback_total=24, mode="image")

    assert values["participation"] == round(5 / 18 * 100, 1)
    assert values["interaction"] == round(2 / 18 * 100, 1)


def test_model_confidence_never_weights_metric_aggregation():
    frames = [
        {
            "metrics": {"focus": 100.0},
            "confidence": 0.99,
            "observationDurationSeconds": 1.0,
        },
        {
            "metrics": {"focus": 0.0},
            "confidence": 0.01,
            "observationDurationSeconds": 1.0,
        },
    ]

    assert aggregate_metric(frames, "focus") == 50.0


def test_sourced_rubric_controls_score_weights_and_alert_targets():
    metrics = {
        "focus": 82.0,
        "participation": 40.0,
        "interaction": 15.0,
        "teacherGuidance": 70.0,
        "teachingRhythm": 60.0,
        "podiumShare": 61.5,
    }
    rubric = {
        "name": "Synthetic rubric",
        "version": "1.0",
        "source": "fixtures/rubric-v1",
        "weights": {
            "focus": 1,
            "participation": 0,
            "interaction": 0,
            "teacherGuidance": 0,
            "teachingRhythm": 0,
        },
        "targets": {"interaction": {"min": 20}, "podiumShare": {"max": 60}},
    }

    result = evaluate_rubric(metrics, rubric)

    assert result["overall"] == metrics["focus"]
    assert result["source"] == "fixtures/rubric-v1"
    assert result["missedTargets"] == ["interaction", "podiumShare"]
