"""Render the versioned thirty-image synthetic visual trial set."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from packages.media_pipeline.tools import resolve_media_tool

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evals" / "media" / "stage5_visual_trials.v1.json"


def generate(output: Path) -> dict[str, object]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    ffmpeg = str(resolve_media_tool("ffmpeg"))
    rendered = []
    for trial in payload["trials"]:
        truth = trial["truth"]
        line_one = (
            f"{trial['trial_id']} RH={truth['raise_hand']} ST={truth['standing']} "
            f"RW={truth['reading_or_writing_visible']}"
        )
        line_two = (
            f"GD={truth['group_discussion_visible']} POD={truth['teacher_at_podium']} "
            f"PAT={truth['teacher_patrolling_visible']}"
        )
        image = output / f"{trial['trial_id']}.png"
        filter_value = (
            "color=c=white:s=960x540:d=1,"
            "drawbox=x=40:y=40:w=880:h=460:color=0x335577:t=5,"
            f"drawtext=text='{line_one}':x=80:y=180:fontsize=38:fontcolor=black,"
            f"drawtext=text='{line_two}':x=80:y=260:fontsize=38:fontcolor=black"
        )
        completed = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                filter_value,
                "-frames:v",
                "1",
                str(image),
            ],
            check=False,
            capture_output=True,
            shell=False,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))
        rendered.append(
            {
                "trial_id": trial["trial_id"],
                "image": str(image.resolve()),
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "truth": truth,
            }
        )
    report = {
        "schema_version": payload["schema_version"],
        "provenance": payload["provenance"],
        "annotation_method": payload["annotation_method"],
        "trial_count": len(rendered),
        "trials": rendered,
    }
    (output / "rendered-manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = generate(args.output.resolve())
    print(json.dumps({"trial_count": report["trial_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
