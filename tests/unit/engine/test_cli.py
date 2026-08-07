import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
IMAGE_FIXTURE = ROOT / "fixtures" / "structured" / "image-demo.json"


def _run_cli(input_path: Path, output_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "packages.evidence_engine.cli",
            "engine",
            "analyze",
            str(input_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_cli_supports_windows_chinese_and_space_paths(tmp_path):
    input_dir = tmp_path / "中文 输入目录"
    input_dir.mkdir()
    input_path = input_dir / "课堂 样例.json"
    input_path.write_bytes(IMAGE_FIXTURE.read_bytes())
    output_path = tmp_path / "中文 输出目录"

    completed = _run_cli(input_path, output_path)

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "succeeded"
    assert summary["analysis_mode"] == "image"
    assert summary["elapsed_seconds"] >= 0
    assert len(summary["artifacts"]) == 5
    assert all(len(item["sha256"]) == 64 for item in summary["artifacts"].values())


def test_cli_returns_nonzero_for_invalid_input_and_preserves_unrelated_file(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"analysisMode": "image"}', encoding="utf-8")
    output = tmp_path / "existing output"
    output.mkdir()
    unrelated = output / "notes.txt"
    unrelated.write_text("do not delete", encoding="utf-8")

    completed = _run_cli(invalid, output)

    assert completed.returncode != 0
    assert json.loads(completed.stderr)["status"] == "error"
    assert unrelated.read_text(encoding="utf-8") == "do not delete"
    assert {path.name for path in output.iterdir()} == {"notes.txt"}
