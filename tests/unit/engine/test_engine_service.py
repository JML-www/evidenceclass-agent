import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from packages.evidence_engine import ARTIFACT_FILENAMES, EvidenceEngineService
from packages.evidence_engine.renderers.common import display_value

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures" / "structured"


def _payload(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("fixture_name", "expected_mode"),
    [("image-demo.json", "image"), ("video-demo.json", "video")],
)
def test_service_writes_exact_five_artifacts_with_verified_hashes(
    tmp_path, fixture_name, expected_mode
):
    output = tmp_path / "中文 空格输出"
    output.mkdir()
    unrelated = output / "keep-me.txt"
    unrelated.write_text("user-owned", encoding="utf-8")

    summary = EvidenceEngineService().analyze_file(FIXTURES / fixture_name, output)

    assert summary.analysis_mode == expected_mode
    assert tuple(summary.artifacts) == ARTIFACT_FILENAMES
    assert unrelated.read_text(encoding="utf-8") == "user-owned"
    assert {path.name for path in output.iterdir()} == {*ARTIFACT_FILENAMES, unrelated.name}
    for filename, artifact in summary.artifacts.items():
        content = (output / filename).read_bytes()
        assert artifact.sha256 == hashlib.sha256(content).hexdigest()
        assert artifact.size_bytes == len(content)


def test_same_input_has_stable_semantic_result_evidence_ids_and_artifacts(tmp_path):
    service = EvidenceEngineService()
    payload = _payload("video-demo.json")

    first_result = service.analyze_payload(payload)
    second_result = service.analyze_payload(payload)

    assert first_result == second_result
    first_ids = [item["evidence_id"] for item in first_result["evidence"]]
    assert first_ids == [item["evidence_id"] for item in second_result["evidence"]]
    assert len(first_ids) == len(set(first_ids))

    first_output = tmp_path / "first"
    second_output = tmp_path / "second"
    service.analyze_file(FIXTURES / "video-demo.json", first_output)
    service.analyze_file(FIXTURES / "video-demo.json", second_output)
    assert {
        name: (first_output / name).read_bytes() for name in ARTIFACT_FILENAMES
    } == {name: (second_output / name).read_bytes() for name in ARTIFACT_FILENAMES}


def test_five_artifacts_share_canonical_metrics_and_evidence(tmp_path):
    output = tmp_path / "artifacts"
    EvidenceEngineService().analyze_file(FIXTURES / "image-demo.json", output)
    data = json.loads((output / "analysis_data.json").read_text(encoding="utf-8"))
    markdown = (output / "classroom_analysis_report.md").read_text(encoding="utf-8")
    html = (output / "dashboard.html").read_text(encoding="utf-8")
    action_rows = list(
        csv.DictReader(io.StringIO((output / "action_and_retest.csv").read_text(encoding="utf-8")))
    )
    evidence_rows = list(
        csv.DictReader(io.StringIO((output / "evidence_ledger.csv").read_text(encoding="utf-8")))
    )

    for action in data["actions"]:
        matching = next(row for row in action_rows if row["action_id"] == action["actionId"])
        expected = "" if action["currentValue"] is None else str(action["currentValue"])
        assert matching["current_value"] == expected
        displayed = display_value(action["currentValue"], "%")
        assert displayed in markdown
        assert displayed in html
    assert [row["evidence_id"] for row in evidence_rows] == [
        item["evidence_id"] for item in data["evidence"]
    ]
    assert data["analysisMode"] == "image"


def test_metrics_and_renderers_keep_their_architecture_boundaries():
    metrics_source = (ROOT / "packages" / "evidence_engine" / "metrics.py").read_text(
        encoding="utf-8"
    )
    assert "pathlib" not in metrics_source
    assert "open(" not in metrics_source
    for renderer in (ROOT / "packages" / "evidence_engine" / "renderers").glob("*_renderer.py"):
        source = renderer.read_text(encoding="utf-8")
        assert "evidence_engine.metrics" not in source
        assert "..metrics" not in source
