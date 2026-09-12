"""Phase-5.5: compare a real VLM against exact ground truth on 30 self-made diagrams.

The fixtures are generated deterministically, so the exact number of drawn student
icons, raised-hand markers, and the teacher posture are known before the model runs.
That makes a real accuracy number possible without using any private classroom media.

Boundary: the fixtures are *self-authored synthetic diagrams*, not real classroom
frames. Every number in the report is therefore a synthetic-fixture number, and the
report says so explicitly.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image, ImageDraw

from packages.model_gateway.contracts import InvocationContext, VisionRequest
from packages.model_gateway.errors import ModelGatewayError
from packages.model_gateway.local_qwen import LocalQwen35Adapter
from packages.model_gateway.raw_responses import DirectoryRawResponseSink

# The canvas must be large enough that every claimed seat is actually drawn. A smaller
# canvas silently clipped the last row, which made the ground truth disagree with the
# image; the grid below fits 6 columns x 4 rows = 24 seats with margin to spare.
WIDTH, HEIGHT = 896, 680

TEACHER_MODES = {
    0: {"label": "blackboard_writing", "expect": {"blackboard_writing": True, "patrolling": False}},
    1: {"label": "patrolling", "expect": {"blackboard_writing": False, "patrolling": True}},
    2: {"label": "slides", "expect": {"blackboard_writing": False, "patrolling": False}},
}


def _spec(index: int) -> dict[str, Any]:
    """Deterministic fixture specification; the ground truth is computed, not guessed."""
    students = 6 + (index % 19)
    raised = index % 5
    mode = index % 3
    return {
        "index": index,
        "visible_student_count": students,
        "hand_raised": raised,
        "teacher_mode": mode,
    }


def _draw(spec: dict[str, Any]) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#f7f7f5")
    draw = ImageDraw.Draw(image)

    board = (40, 28, WIDTH - 40, 170)
    draw.rectangle(board, fill="#2f3a34", outline="#1c231f", width=2)
    if spec["teacher_mode"] == 0:
        for offset in range(7):
            x = 90 + offset * 100
            draw.line((x, 70, x + 66, 140), fill="#e8e4d8", width=5)
    if spec["teacher_mode"] == 2:
        draw.rectangle((160, 56, WIDTH - 160, 148), fill="#dfe8f5", outline="#4a6fa5", width=4)
        for index in range(4):
            y = 74 + index * 18
            draw.line((190, y, WIDTH - 190, y), fill="#2b3a52", width=7)

    students = spec["visible_student_count"]
    columns = 6
    left0, top0, cell_x, cell_y = 80, 300, 110, 96
    seats: list[tuple[int, int]] = []
    for seat in range(students):
        row, column = divmod(seat, columns)
        seats.append((left0 + column * cell_x, top0 + row * cell_y))

    for seat_index, (x, y) in enumerate(seats):
        draw.rectangle((x, y, x + 50, y + 42), fill="#14171a", outline="#000000", width=2)
        if seat_index < spec["hand_raised"]:
            # A thick stem plus a solid head, well separated from the seat so a small
            # vision encoder can still resolve it after downscaling.
            draw.line((x + 25, y - 6, x + 25, y - 34), fill="#d02020", width=8)
            draw.ellipse((x + 15, y - 48, x + 35, y - 28), fill="#d02020")

    if spec["teacher_mode"] == 1:
        # Standing in the aisle between the second and third seat rows.
        draw.rectangle((WIDTH // 2 - 26, 470, WIDTH // 2 + 26, 546), fill="#2b6cb0")
    elif spec["teacher_mode"] == 2:
        draw.rectangle((WIDTH - 132, 210, WIDTH - 70, 292), fill="#2b6cb0")
    else:
        draw.rectangle((66, 196, 130, 278), fill="#2b6cb0")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


# Kept deliberately short. A 0.8B model echoes long instructions back as its
# "evidence" and "limitations" instead of observing the image, which the first run of
# this evaluation demonstrated; terse, concrete wording is the difference between a
# usable observation and a paraphrase of the prompt.
INSTRUCTION = (
    "Synthetic diagram, no real people. Blue rectangle: teacher. "
    "Dark squares: students. Red mark above a square: raised hand. "
    "Count the icons visible in this image."
)


def _evaluate(
    records: list[dict[str, Any]], total: int, failures: dict[str, int]
) -> dict[str, Any]:
    scored = [item for item in records if item["status"] == "succeeded"]
    student_pairs = [
        (item["predicted"]["visible_student_count"], item["truth"]["visible_student_count"])
        for item in scored
    ]
    hand_pairs = [
        (item["predicted"]["hand_raised"], item["truth"]["hand_raised"]) for item in scored
    ]
    teacher_hits = [
        item["predicted"]["teacher_patrolling"] == item["truth"]["teacher_patrolling"]
        and item["predicted"]["teacher_blackboard_writing"]
        == item["truth"]["teacher_blackboard_writing"]
        for item in scored
    ]
    return {
        "images": total,
        "succeeded": len(scored),
        "schema_first_pass_rate": len(scored) / total if total else 0.0,
        "failure_classification": dict(sorted(failures.items())),
        "visible_student_count": _pair_metrics(student_pairs),
        "hand_raised": _pair_metrics(hand_pairs),
        "teacher_posture_accuracy": (
            sum(teacher_hits) / len(teacher_hits) if teacher_hits else None
        ),
        "accuracy_claimed_as_classroom": False,
    }


def _pair_metrics(pairs: list[tuple[int, int]]) -> dict[str, Any]:
    if not pairs:
        return {"n": 0, "exact_match_rate": None, "mae": None, "bias": None}
    exact = sum(1 for predicted, truth in pairs if predicted == truth) / len(pairs)
    errors = [predicted - truth for predicted, truth in pairs]
    return {
        "n": len(pairs),
        "exact_match_rate": round(exact, 4),
        "mae": round(mean(abs(value) for value in errors), 3),
        "bias": round(mean(errors), 3),
    }


def run(*, model_path: Path, output_dir: Path, count: int = 30) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter = LocalQwen35Adapter(
        model_path=model_path,
        raw_response_sink=DirectoryRawResponseSink(output_dir / "raw-responses"),
    )
    failures: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    for index in range(count):
        spec = _spec(index)
        png = _draw(spec)
        (output_dir / "fixtures").mkdir(parents=True, exist_ok=True)
        (output_dir / "fixtures" / f"classroom-{index:02d}.png").write_bytes(png)
        request = VisionRequest(
            image_refs=[_data_url(png)],
            instruction=INSTRUCTION,
            context=InvocationContext(
                prompt_version="stage5-real-vlm-comparison.v0.1",
                config_version="stage5-real-vlm-comparison.v0.1",
                timeout_seconds=90.0,
                max_output_tokens=700,
            ),
        )
        try:
            result = adapter.observe(request)
        except ModelGatewayError as exc:
            failures[exc.error_code] = failures.get(exc.error_code, 0) + 1
            records.append(
                {
                    "index": index,
                    "status": "failed",
                    "error_code": exc.error_code,
                    "truth": _truth(spec),
                }
            )
            continue
        observation = result.parsed.observation
        mode = TEACHER_MODES[spec["teacher_mode"]]["expect"]
        records.append(
            {
                "index": index,
                "status": "succeeded",
                "latency_ms": result.metadata.latency_ms,
                "model_revision": result.metadata.model_revision,
                "output_tokens": result.metadata.usage.output_tokens,
                "truth": _truth(spec),
                "predicted": {
                    "visible_student_count": observation.visible_student_count,
                    "hand_raised": observation.hand_raised,
                    "teacher_patrolling": observation.teacher.patrolling,
                    "teacher_blackboard_writing": observation.teacher.blackboard_writing,
                    "teacher_using_slides": observation.teacher.using_slides,
                    "teacher_teaching": observation.teacher.teaching,
                    "confidence": observation.confidence,
                },
            }
        )
        print(
            f"[{index + 1:02d}/{count}] truth={spec['visible_student_count']} students/"
            f"{spec['hand_raised']} hands/{TEACHER_MODES[spec['teacher_mode']]['label']} -> "
            f"pred={observation.visible_student_count}/{observation.hand_raised} "
            f"mode={mode}",
            flush=True,
        )
    report = {
        "schema_version": "stage5-real-vlm.v0.1",
        "fixture": {
            "authorized": True,
            "synthetic": True,
            "source": "self-authored deterministic classroom diagrams",
            "count": count,
            "ground_truth": "computed from the generator, not hand-labelled",
        },
        "claim_boundary": (
            "Accuracy is measured on synthetic diagrams only. It is NOT classroom accuracy and "
            "must not be reported as such."
        ),
        "model": f"temporary-local:{model_path.name}",
        "evaluation": _evaluate(records, count, failures),
        "records": records,
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def _truth(spec: dict[str, Any]) -> dict[str, Any]:
    expect = TEACHER_MODES[spec["teacher_mode"]]["expect"]
    return {
        "visible_student_count": spec["visible_student_count"],
        "hand_raised": spec["hand_raised"],
        "teacher_mode": TEACHER_MODES[spec["teacher_mode"]]["label"],
        "teacher_patrolling": expect["patrolling"],
        "teacher_blackboard_writing": expect["blackboard_writing"],
    }


def render_markdown(report: dict[str, Any]) -> str:
    evaluation = report["evaluation"]
    students = evaluation["visible_student_count"]
    hands = evaluation["hand_raised"]
    lines = [
        "# Phase 5.5 - real VLM comparison on 30 synthetic classroom diagrams",
        "",
        "Boundary: the 30 fixtures are self-authored deterministic diagrams. The ground truth is",
        "computed by the generator. **No number below is classroom accuracy.**",
        "",
        f"- model: `{report['model']}`",
        f"- images: {evaluation['images']}",
        f"- schema first-pass rate: {evaluation['schema_first_pass_rate']:.3f}",
        f"- failure classification: `{evaluation['failure_classification']}`",
        "",
        "| quantity | n | exact-match | MAE | bias |",
        "| --- | --- | --- | --- | --- |",
        f"| visible_student_count | {students['n']} | {students['exact_match_rate']} | "
        f"{students['mae']} | {students['bias']} |",
        f"| hand_raised | {hands['n']} | {hands['exact_match_rate']} | {hands['mae']} | "
        f"{hands['bias']} |",
        "",
        f"- teacher posture accuracy (patrolling + blackboard_writing both correct): "
        f"{evaluation['teacher_posture_accuracy']}",
        "",
        "## Per-image detail",
        "",
        "| # | truth students | pred students | truth hands | pred hands | teacher mode |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["records"]:
        if item["status"] != "succeeded":
            lines.append(f"| {item['index']} | - | FAILED {item['error_code']} | - | - | - |")
            continue
        lines.append(
            f"| {item['index']} | {item['truth']['visible_student_count']} | "
            f"{item['predicted']['visible_student_count']} | {item['truth']['hand_raised']} | "
            f"{item['predicted']['hand_raised']} | {item['truth']['teacher_mode']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=30)
    args = parser.parse_args()
    report = run(model_path=args.model_path, output_dir=args.output.resolve(), count=args.count)
    markdown = args.output.resolve() / "report.md"
    markdown.write_text(render_markdown(report), encoding="utf-8")
    payload = {"report": str(markdown), "evaluation": report["evaluation"]}
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
