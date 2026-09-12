"""Phase-11.2: inter-annotator agreement between two independent automated annotators.

Design
------

Two annotators label the same 30 synthetic classroom units. Neither one is the generator's
ground truth, so the agreement measured here is genuine inter-annotator agreement rather than
"accuracy against the answer key".

* **Annotator A - pixel rule.** Reads the rendered PNG and decides the teacher posture from the
  board region's colour statistics: many chalk-white pixels means writing on the board, a large
  light-blue rectangle means slides are displayed, neither means the teacher is elsewhere.
  It also decides hand-raise presence by counting red marker pixels.
* **Annotator B - local VLM.** The structured observation produced by the local Qwen3.5-0.8B
  adapter, mapped onto the same category sets.

Honest boundary
---------------

**Neither annotator is a human.** This is an automated agreement study. It shows whether the
local model agrees with an independent deterministic observer, which is a reproducibility and
consistency signal, not a human-labelling quality signal. A human double-annotation round is
still outstanding and is recorded as such in the report.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

# Board colour probes, matching evals/media/run_stage5_vision_eval.py.
CHALK = (232, 228, 216)
SLIDE = (223, 232, 245)
HAND = (208, 32, 32)

CHALK_MIN_PIXELS = 900
SLIDE_MIN_PIXELS = 4_000
HAND_MIN_PIXELS = 150
TOLERANCE = 24

POSTURE_CATEGORIES = ("blackboard_writing", "patrolling", "slides", "unclear")
HAND_CATEGORIES = ("absent", "present", "unclear")

BOARD_BOX = (40, 28, 856, 170)


def _near(pixel: tuple[int, int, int], target: tuple[int, int, int]) -> bool:
    return all(abs(a - b) <= TOLERANCE for a, b in zip(pixel, target, strict=True))


def _count(pixels: list[tuple[int, int, int]], target: tuple[int, int, int]) -> int:
    return sum(1 for pixel in pixels if _near(pixel, target))


def annotate_a(image_path: Path) -> dict[str, str]:
    """Deterministic pixel-rule annotator."""

    with Image.open(image_path) as handle:
        rgb = handle.convert("RGB")
        board = list(rgb.crop(BOARD_BOX).getdata())
        full = list(rgb.getdata())
    chalk = _count(board, CHALK)
    slide = _count(board, SLIDE)
    if chalk >= CHALK_MIN_PIXELS:
        posture = "blackboard_writing"
    elif slide >= SLIDE_MIN_PIXELS:
        posture = "slides"
    else:
        posture = "patrolling"
    hand = "present" if _count(full, HAND) >= HAND_MIN_PIXELS else "absent"
    return {"teacher_posture": posture, "hand_raised": hand}


def annotate_b(record: dict[str, Any]) -> dict[str, str]:
    """Map one real-VLM record onto the same categories; a failed call is 'unclear'."""

    if record.get("status") != "succeeded":
        return {"teacher_posture": "unclear", "hand_raised": "unclear"}
    predicted = record["predicted"]
    if predicted["teacher_blackboard_writing"]:
        posture = "blackboard_writing"
    elif predicted.get("teacher_using_slides"):
        posture = "slides"
    elif predicted["teacher_patrolling"]:
        posture = "patrolling"
    else:
        posture = "unclear"
    hand = "present" if predicted["hand_raised"] > 0 else "absent"
    return {"teacher_posture": posture, "hand_raised": hand}


def cohen_kappa(pairs: list[tuple[str, str]], categories: tuple[str, ...]) -> dict[str, Any]:
    """Cohen's kappa with the observed/expected decomposition spelled out."""

    total = len(pairs)
    if total == 0:
        return {"n": 0, "observed_agreement": None, "expected_agreement": None, "kappa": None}
    matrix = {a: dict.fromkeys(categories, 0) for a in categories}
    for left, right in pairs:
        matrix[left][right] += 1
    observed = sum(matrix[c][c] for c in categories) / total
    left_marginal = Counter(left for left, _ in pairs)
    right_marginal = Counter(right for _, right in pairs)
    expected = sum(
        (left_marginal[c] / total) * (right_marginal[c] / total) for c in categories
    )
    kappa = None if expected >= 1.0 else (observed - expected) / (1.0 - expected)
    return {
        "n": total,
        "observed_agreement": round(observed, 4),
        "expected_agreement": round(expected, 4),
        "kappa": None if kappa is None else round(kappa, 4),
        "confusion_matrix": matrix,
    }


def _interpret(kappa: float | None) -> str:
    if kappa is None:
        return "undefined"
    if kappa < 0.0:
        return "poor (worse than chance)"
    if kappa < 0.21:
        return "slight"
    if kappa < 0.41:
        return "fair"
    if kappa < 0.61:
        return "moderate"
    if kappa < 0.81:
        return "substantial"
    return "almost perfect"


def run(*, report_path: Path, fixtures_dir: Path, output_dir: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    records = report["records"]
    posture_pairs: list[tuple[str, str]] = []
    hand_pairs: list[tuple[str, str]] = []
    units: list[dict[str, Any]] = []
    for record in records:
        index = record["index"]
        image = fixtures_dir / f"classroom-{index:02d}.png"
        if not image.is_file():
            continue
        left = annotate_a(image)
        right = annotate_b(record)
        posture_pairs.append((left["teacher_posture"], right["teacher_posture"]))
        hand_pairs.append((left["hand_raised"], right["hand_raised"]))
        units.append(
            {
                "index": index,
                "annotator_a": left,
                "annotator_b": right,
                "generator_truth_mode": record["truth"]["teacher_mode"],
                "generator_truth_raised": record["truth"]["hand_raised"],
            }
        )

    # Secondary signal: how often does each annotator match the generator's own record?
    truth_mode_agreement = {
        "annotator_a": _agreement(
            [
                (unit["annotator_a"]["teacher_posture"], unit["generator_truth_mode"])
                for unit in units
            ]
        ),
        "annotator_b": _agreement(
            [
                (unit["annotator_b"]["teacher_posture"], unit["generator_truth_mode"])
                for unit in units
            ]
        ),
    }
    report_out = {
        "report_version": "annotation-report.v1",
        "label_schema_version": "observable-classroom-labels.v1",
        "units": len(units),
        "annotators": {
            "A": {
                "kind": "automated",
                "method": "deterministic pixel-rule observer over the rendered fixture",
                "human": False,
            },
            "B": {
                "kind": "automated",
                "method": "local Qwen3.5-0.8B structured vision observation",
                "human": False,
            },
        },
        "human_annotation_outstanding": True,
        "teacher_posture": cohen_kappa(posture_pairs, POSTURE_CATEGORIES),
        "hand_raised": cohen_kappa(hand_pairs, HAND_CATEGORIES),
        "agreement_with_generator_truth": truth_mode_agreement,
        "model_source_report": str(report_path),
        "units_detail": units,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "annotation-kappa-v1.json").write_text(
        json.dumps(report_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report_out


def _agreement(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    return round(sum(1 for left, right in pairs if left == right) / len(pairs), 4)


def render_markdown(report: dict[str, Any]) -> str:
    posture = report["teacher_posture"]
    hand = report["hand_raised"]
    lines = [
        "# 阶段十一 · 标注一致性报告 v1",
        "",
        "## 这份报告是什么，不是什么",
        "",
        "在两个**独立**的自动标注器之间测一致性，而不是测「标注员对不对」。",
        "",
        "- **标注器 A（规则式）**：读渲染出的 PNG，按讲台区域的像素颜色统计判断教师姿态；"
        "按红色标记像素量判断有无举手。",
        "- **标注器 B（本地模型）**：本地 Qwen3.5-0.8B 的结构化视觉输出，映射到同一套类别。",
        "",
        f"> **两个标注器都不是人类。** 这是自动一致性研究，反映的是可复现性与一致性信号，"
        f"不能替代人工标注质量。**人类双标轮次仍未执行**"
        f"（`human_annotation_outstanding: "
        f"{str(report['human_annotation_outstanding']).lower()}`）。",
        "",
        f"- 标注单元数：**{report['units']}**",
        f"- 模型来源报告：`{report['model_source_report']}`",
        "",
        "## 教师姿态一致性（4 类）",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
        f"| 观测一致度 (Po) | {posture['observed_agreement']} |",
        f"| 期望一致度 (Pe) | {posture['expected_agreement']} |",
        f"| **Cohen's kappa** | **{posture['kappa']}** |",
        f"| 解释 | {_interpret(posture['kappa'])} |",
        "",
        "混淆矩阵（行 = 标注器 A，列 = 标注器 B）：",
        "",
        "| A \\ B | " + " | ".join(POSTURE_CATEGORIES) + " |",
        "| --- | " + " | ".join("---" for _ in POSTURE_CATEGORIES) + " |",
    ]
    for row in POSTURE_CATEGORIES:
        cells = " | ".join(str(posture["confusion_matrix"][row][col]) for col in POSTURE_CATEGORIES)
        lines.append(f"| {row} | {cells} |")
    lines += [
        "",
        "## 举手有无一致性（2 类）",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
        f"| 观测一致度 (Po) | {hand['observed_agreement']} |",
        f"| 期望一致度 (Pe) | {hand['expected_agreement']} |",
        f"| **Cohen's kappa** | **{hand['kappa']}** |",
        f"| 解释 | {_interpret(hand['kappa'])} |",
        "",
        "## 与生成器记录的对照（次要信号）",
        "",
        "生成器记录不是人工真值，只是构造素材时写入的姿态标签。列在这里是为了说明"
        "两个标注器各自的偏差方向，而不是当作准确率。",
        "",
        "| 标注器 | 与生成器记录一致率 |",
        "| --- | --- |",
        f"| A（规则式） | {report['agreement_with_generator_truth']['annotator_a']} |",
        f"| B（本地模型） | {report['agreement_with_generator_truth']['annotator_b']} |",
        "",
        "## 逐单元明细",
        "",
        "| # | A 姿态 | B 姿态 | A 举手 | B 举手 | 生成器记录姿态 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for unit in report["units_detail"]:
        lines.append(
            f"| {unit['index']} | {unit['annotator_a']['teacher_posture']} | "
            f"{unit['annotator_b']['teacher_posture']} | {unit['annotator_a']['hand_raised']} | "
            f"{unit['annotator_b']['hand_raised']} | {unit['generator_truth_mode']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("runs/stage-5/real-vlm-30-fixed/report.json"),
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("runs/stage-5/real-vlm-30-fixed/fixtures"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("evals/reports"))
    parser.add_argument(
        "--markdown", type=Path, default=Path("docs/evaluation/annotation-report-v1.md")
    )
    args = parser.parse_args()
    report = run(
        report_path=args.report.resolve(),
        fixtures_dir=args.fixtures.resolve(),
        output_dir=args.output_dir.resolve(),
    )
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "units": report["units"],
                "posture_kappa": report["teacher_posture"]["kappa"],
                "hand_kappa": report["hand_raised"]["kappa"],
                "markdown": str(args.markdown),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
