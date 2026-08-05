import json
from pathlib import Path
from packages.evidence_engine.validator import validate_payload

# 1. test_invisible_region_cannot_have_numbers
def test_invisible_region_cannot_have_numbers():
    """不可见区域不允许量化数值，校验拦截"""
    payload = json.loads(Path("fixtures/image-demo.json").read_text(encoding="utf-8"))
    payload["regionHeatmap"]["back"]["focus"] = 80
    try:
        validate_payload(payload)
        assert False, "预期抛出ValueError"
    except ValueError:
        pass

# 2. test_methodology_reference_documents_validation_boundary
def test_methodology_reference_documents_validation_boundary():
    """参考文档约束指标不得输出准确率类结论"""
    ref_text = Path("docs/references/methodology.md").read_text(encoding="utf-8")
    assert "10.1787/9789264043466-en" in ref_text
    assert "10.1177/001316446002000104" in ref_text
    assert "不报告准确率" in ref_text