"""Expand the deterministic perception fixture track from 30 to 120 vision cases.

What this file produces and what it does *not* produce
-----------------------------------------------------

It produces **fixture** records: synthetic cases whose six behaviour labels are drawn
from a seeded generator, plus a baseline prediction produced by a documented,
deterministic observer error model. It exercises the perception evaluator over a
larger sample and gives phase 11 a stable regression baseline.

It does **not** measure any model. Every generated record carries ``real_model: false``,
so ``evaluate_vision`` keeps ``accuracy_claimed`` false for the fixture track. The real
VLM measurement lives in a separate track produced by
``evals/media/run_stage5_vision_eval.py`` and is reported separately.

The existing 30 records are preserved byte-for-byte; new cases are appended with
``vision-031``.. ``vision-120`` identifiers.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

LABELS: tuple[str, ...] = (
    "raise_hand",
    "standing",
    "reading_or_writing_visible",
    "group_discussion_visible",
    "teacher_at_podium",
    "teacher_patrolling_visible",
)

#: Deterministic baseline observer. These are the *documented* confusions of the
#: fixture observer, not a model's error rate: the fixture baseline misses a thin
#: raised-hand marker at a fixed rate and under-counts a crowded row. They exist so
#: the evaluator is exercised by imperfect input instead of a perfect copy of truth.
MISS_RATE_RAISE_HAND = 0.18
MISS_RATE_CROWDED_ROW = 0.12
FALSE_POSITIVE_RATE_DISCUSSION = 0.09
CROWDED_ROW_THRESHOLD = 8

SEED = 20260812
TARGET_VISION_CASES = 120


def _truth(spec: dict[str, int], rng: random.Random) -> dict[str, int]:
    """Derive the six labels from one generated classroom unit."""

    students = spec["students"]
    truth = {
        "raise_hand": spec["raised"],
        "standing": spec["standing"],
        "reading_or_writing_visible": spec["reading"],
        "group_discussion_visible": spec["discussion"],
        "teacher_at_podium": 1 if spec["teacher_mode"] == "podium" else 0,
        "teacher_patrolling_visible": 1 if spec["teacher_mode"] == "patrolling" else 0,
    }
    # A label can never describe more students than are visible.
    for label in ("raise_hand", "standing", "reading_or_writing_visible"):
        truth[label] = min(truth[label], students)
    return truth


def _baseline(truth: dict[str, int], students: int, rng: random.Random) -> dict[str, int]:
    """Apply the documented fixture-observer error model to the truth."""

    prediction = dict(truth)
    if prediction["raise_hand"] and rng.random() < MISS_RATE_RAISE_HAND:
        prediction["raise_hand"] = max(0, prediction["raise_hand"] - 1)
    if students >= CROWDED_ROW_THRESHOLD:
        target = "standing" if prediction["standing"] else "reading_or_writing_visible"
        if prediction[target] and rng.random() < MISS_RATE_CROWDED_ROW:
            prediction[target] -= 1
    if rng.random() < FALSE_POSITIVE_RATE_DISCUSSION:
        prediction["group_discussion_visible"] += 1
    return prediction


def _spec(index: int, rng: random.Random) -> dict[str, int | str]:
    students = rng.randint(6, 24)
    teacher_mode = rng.choice(("podium", "patrolling"))
    return {
        "students": students,
        "raised": rng.randint(0, min(5, students)),
        "standing": rng.randint(0, min(4, students)),
        "reading": rng.randint(0, min(9, students)),
        "discussion": rng.randint(0, 3),
        "teacher_mode": teacher_mode,
    }


def generate(
    existing: list[dict[str, Any]], target: int = TARGET_VISION_CASES
) -> list[dict[str, Any]]:
    """Return the full vision track: existing records plus generated ones."""

    vision = [record for record in existing if "truth" in record]
    if len(vision) >= target:
        return vision
    rng = random.Random(SEED)
    start = len(vision) + 1
    generated: list[dict[str, Any]] = []
    for offset in range(target - len(vision)):
        index = start + offset
        spec = _spec(index, rng)
        truth = _truth(spec, rng)  # type: ignore[arg-type]
        generated.append(
            {
                "case_id": f"vision-{index:03d}",
                "truth": truth,
                "prediction": _baseline(truth, int(spec["students"]), rng),
                "real_model": False,
                "fixture": {
                    "synthetic": True,
                    "generator": "run_stage11_expand_perception",
                    "seed": SEED,
                    "visible_student_count": spec["students"],
                    "teacher_mode": spec["teacher_mode"],
                },
            }
        )
    return vision + generated


def run(dataset_path: Path) -> dict[str, Any]:
    existing = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    vision = generate(existing)
    others = [record for record in existing if "truth" not in record]
    ordered = others + vision
    payload = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in ordered
    )
    dataset_path.write_text(payload, encoding="utf-8")
    return {
        "dataset": str(dataset_path),
        "vision_cases": len(vision),
        "other_cases": len(others),
        "total": len(ordered),
        "real_model_records": sum(1 for record in vision if record.get("real_model")),
        "seed": SEED,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/datasets/perception.v1.jsonl"),
    )
    args = parser.parse_args()
    print(json.dumps(run(args.dataset), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
