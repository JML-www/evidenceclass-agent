"""Offline, evidence-preserving metrics for visual, ASR, OCR and structure outputs.

The evaluator accepts JSON-compatible records and never treats an unknown prediction as a
correct negative.  This is intentionally independent of model providers so that Fake and real
model runs produce comparable reports.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from packages.media_pipeline.evaluation import _edit_counts
from packages.media_pipeline.vision import ALLOWED_LABELS


class PerceptionCase(dict):
    """A small mapping alias used by callers that stream JSONL records."""


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    raise ValueError("evaluation records must be a list of objects")


def _binary_metrics(truth: Iterable[bool], prediction: Iterable[bool]) -> dict[str, float]:
    tp = fp = fn = 0
    for expected, actual in zip(truth, prediction, strict=True):
        if expected and actual:
            tp += 1
        elif not expected and actual:
            fp += 1
        elif expected and not actual:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "support": float(tp + fn)}


def evaluate_vision(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute six-label precision/recall/F1 and count MAE with unknown accounting."""
    if len(records) < 30:
        raise ValueError("vision evaluation requires at least 30 records")
    per_label: dict[str, dict[str, float]] = {}
    mae: dict[str, float] = {}
    unknown: dict[str, float] = {}
    errors: list[str] = []
    for label in ALLOWED_LABELS:
        truth_presence = []
        pred_presence = []
        abs_errors: list[float] = []
        unknown_count = 0
        for index, record in enumerate(records):
            truth = record.get("truth", {})
            prediction = record.get("prediction", {})
            expected = truth.get(label)
            actual = prediction.get(label)
            if not isinstance(expected, (int, float)) or expected < 0:
                raise ValueError(f"truth.{label} must be a non-negative count")
            if actual is None:
                unknown_count += 1
                continue
            if isinstance(actual, bool) or not isinstance(actual, (int, float)) or actual < 0:
                raise ValueError(f"prediction.{label} must be a non-negative count or null")
            truth_presence.append(expected > 0)
            pred_presence.append(actual > 0)
            abs_errors.append(abs(float(expected) - float(actual)))
            if expected != actual:
                errors.append(str(record.get("case_id", index)))
        per_label[label] = _binary_metrics(truth_presence, pred_presence)
        mae[label] = sum(abs_errors) / len(abs_errors) if abs_errors else None
        unknown[label] = unknown_count / len(records)
    macro = {
        key: sum(item[key] for item in per_label.values()) / len(per_label)
        for key in ("precision", "recall", "f1")
    }
    return {
        "trial_count": len(records),
        "labels": per_label,
        "macro": macro,
        "count_mae_by_label": mae,
        "unknown_rate_by_label": unknown,
        "error_case_ids": sorted(set(errors)),
        "accuracy_claimed": bool(records[0].get("real_model", False)),
    }


def evaluate_asr(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("ASR evaluation requires at least one manually transcribed record")
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    errors: list[str] = []
    for index, record in enumerate(records):
        category = str(record.get("category", "unknown"))
        reference = str(record.get("reference", ""))
        hypothesis = str(record.get("hypothesis", ""))
        if not reference:
            raise ValueError("ASR reference cannot be empty")
        distance, length = _edit_counts(reference, hypothesis)
        totals[category][0] += distance
        totals[category][1] += length
        if distance:
            errors.append(str(record.get("case_id", index)))
    total_distance = sum(item[0] for item in totals.values())
    total_length = sum(item[1] for item in totals.values())
    return {
        "sample_count": len(records),
        "cer": total_distance / max(1, total_length),
        "cer_by_category": {
            category: distance / max(1, length)
            for category, (distance, length) in sorted(totals.items())
        },
        "error_case_ids": errors,
        "accuracy_claimed": False,
    }


def evaluate_ocr(records: list[dict[str, Any]]) -> dict[str, Any]:
    required = {"slide", "board", "no_text"}
    if not records or {str(item.get("category")) for item in records} != required:
        raise ValueError("OCR evaluation must include slide, board, and no_text categories")
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    counts: dict[str, int] = defaultdict(int)
    false_positive = 0
    errors: list[str] = []
    for index, record in enumerate(records):
        category = str(record["category"])
        reference = str(record.get("reference", ""))
        hypothesis = str(record.get("hypothesis", ""))
        counts[category] += 1
        if category == "no_text":
            if hypothesis.strip():
                false_positive += 1
                errors.append(str(record.get("case_id", index)))
            continue
        distance, length = _edit_counts(reference, hypothesis)
        totals[category][0] += distance
        totals[category][1] += length
        if distance:
            errors.append(str(record.get("case_id", index)))
    return {
        "trial_count_by_category": dict(sorted(counts.items())),
        "cer_by_category": {
            category: totals[category][0] / max(1, totals[category][1])
            for category in ("board", "slide")
        },
        "no_text_false_positive_rate": false_positive / counts["no_text"],
        "error_case_ids": errors,
        "accuracy_claimed": False,
    }


def evaluate_structure(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("structure evaluation requires records")
    required = {"case_id", "expected", "actual"}
    valid = 0
    missing = 0
    wrong_type = 0
    overclaim = 0
    failures: list[str] = []
    for record in records:
        case_id = str(record.get("case_id", "unknown"))
        expected = record.get("expected", {})
        actual = record.get("actual", {})
        if not required - set(record) and isinstance(expected, dict) and isinstance(actual, dict):
            valid += 1
            for key, value in expected.items():
                if key not in actual:
                    missing += 1
                    failures.append(case_id)
                elif (
                    value is not None
                    and actual[key] is not None
                    and type(value) is not type(actual[key])
                ):
                    wrong_type += 1
            if actual.get("citation_ids") and not actual.get("evidence_ids"):
                overclaim += 1
        else:
            failures.append(case_id)
    return {
        "record_count": len(records),
        "schema_valid_rate": valid / len(records),
        "missing_field_rate": missing / max(1, len(records)),
        "wrong_type_count": wrong_type,
        "unsupported_evidence_overclaim_count": overclaim,
        "failed_case_ids": sorted(set(failures)),
    }


def evaluate_perception(dataset: dict[str, Any]) -> dict[str, Any]:
    """Evaluate all perception tracks from one versioned dataset object."""
    result: dict[str, Any] = {"dataset_version": dataset.get("dataset_version", "unknown")}
    if "vision" in dataset:
        result["vision"] = evaluate_vision(_as_list(dataset["vision"]))
    if "asr" in dataset:
        result["asr"] = evaluate_asr(_as_list(dataset["asr"]))
    if "ocr" in dataset:
        result["ocr"] = evaluate_ocr(_as_list(dataset["ocr"]))
    if "structure" in dataset:
        result["structure"] = evaluate_structure(_as_list(dataset["structure"]))
    return result
