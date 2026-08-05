import json
from copy import deepcopy
from pathlib import Path

import pytest

from packages.evidence_engine.validation import mode_capabilities, validate_payload

ROOT = Path(__file__).resolve().parents[3]
IMAGE_FIXTURE = ROOT / "fixtures" / "structured" / "image-demo.json"


def _image_payload() -> dict:
    return json.loads(IMAGE_FIXTURE.read_text(encoding="utf-8"))


def test_image_mode_disables_whole_lesson_metrics():
    payload = _image_payload()

    capabilities = mode_capabilities(payload)

    assert capabilities == {
        "wholeLessonMetrics": False,
        "timeline": False,
        "behaviorDistribution": False,
        "positionDistribution": False,
    }
    assert len(payload["frames"]) == 1
    assert payload["regionHeatmap"]["back"] == {
        "visibility": "not_visible",
        "focus": None,
        "interaction": None,
    }


def test_image_mode_rejects_temporal_observations():
    with_asr = _image_payload()
    with_asr["asrSummary"] = {"teacherQuestionCount": 1}

    with pytest.raises(ValueError, match="asrSummary"):
        validate_payload(with_asr)

    with_teacher_event = deepcopy(_image_payload())
    with_teacher_event["frames"][0]["teacher_behaviors"]["questioning"] = True

    with pytest.raises(ValueError, match="temporal teacher behavior"):
        validate_payload(with_teacher_event)
