import json
from pathlib import Path

import pytest

from packages.evidence_engine.validation import validate_payload

ROOT = Path(__file__).resolve().parents[3]
IMAGE_FIXTURE = ROOT / "fixtures" / "structured" / "image-demo.json"
METHODOLOGY = ROOT / "docs" / "references" / "methodology.md"


def test_not_visible_region_rejects_numeric_metrics():
    payload = json.loads(IMAGE_FIXTURE.read_text(encoding="utf-8"))
    payload["regionHeatmap"]["back"]["focus"] = 80

    with pytest.raises(ValueError, match="not-visible region back"):
        validate_payload(payload)


def test_methodology_states_validation_and_accuracy_boundaries():
    reference = METHODOLOGY.read_text(encoding="utf-8")

    assert "10.1787/9789264043466-en" in reference
    assert "10.1177/001316446002000104" in reference
    assert "不报告准确率" in reference
