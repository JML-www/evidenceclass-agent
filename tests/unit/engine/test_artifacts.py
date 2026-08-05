from pathlib import Path

from packages.evidence_engine.artifacts import anonymize
from packages.media_pipeline.showcase import build_windows

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_CONTRACT = ROOT / "docs" / "contracts" / "artifact-contract.md"


def test_artifact_contract_is_a_single_versioned_source():
    contract = ARTIFACT_CONTRACT.read_text(encoding="utf-8")
    expected = {
        "dashboard.html",
        "classroom_analysis_report.md",
        "evidence_ledger.csv",
        "action_and_retest.csv",
        "analysis_data.json",
    }

    assert all(contract.count(f"`{name}`") == 1 for name in expected)
    assert "`analysisMode`" in contract


def test_anonymization_removes_direct_identifiers_and_local_paths():
    raw = {
        "studentName": "Example Student",
        "nested": {"student_id": "SYNTHETIC-001"},
        "sourceFiles": [
            {"name": "video-sample-001.mp4", "localPath": "X:/private/video-sample-001.mp4"}
        ],
    }

    clean = anonymize(raw)

    assert "studentName" not in clean
    assert "student_id" not in clean["nested"]
    assert "localPath" not in clean["sourceFiles"][0]
    assert clean["sourceFiles"][0]["name"] == "video-sample-001.mp4"


def test_showcase_windows_keep_global_timeline_offsets():
    windows = build_windows(["00:02:00", "00:08:00"], clip_seconds=30, lead_seconds=15)

    assert windows[0]["globalStartSeconds"] == 105.0
    assert windows[0]["referenceSeconds"] == 120.0
    assert windows[1]["index"] == 2
