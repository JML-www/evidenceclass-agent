"""Honest ASR, OCR, and six-label trial metrics for phase-5 acceptance."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .vision import ALLOWED_LABELS


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


AsrErrorCategory = Literal["noise", "proper_noun", "overlap", "clean"]


class AsrReferenceSample(_StrictModel):
    sample_id: str = Field(min_length=1)
    category: AsrErrorCategory
    reference: str = Field(min_length=1)
    hypothesis: str


class AsrEvaluation(_StrictModel):
    source_duration_seconds: float = Field(ge=300.0, le=600.0)
    manually_transcribed_sample_count: int = Field(ge=1)
    overall_cer: float = Field(ge=0.0)
    cer_by_category: dict[str, float]
    error_counts_by_category: dict[str, int]
    accuracy_claimed: Literal[False] = False


def evaluate_asr(
    samples: list[AsrReferenceSample], *, source_duration_seconds: float
) -> AsrEvaluation:
    if not samples:
        raise ValueError("at least one manually transcribed ASR sample is required")
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    all_errors = 0
    all_reference = 0
    for sample in samples:
        errors, reference_length = _edit_counts(sample.reference, sample.hypothesis)
        totals[sample.category][0] += errors
        totals[sample.category][1] += reference_length
        all_errors += errors
        all_reference += reference_length
    return AsrEvaluation(
        source_duration_seconds=source_duration_seconds,
        manually_transcribed_sample_count=len(samples),
        overall_cer=all_errors / max(1, all_reference),
        cer_by_category={key: value[0] / max(1, value[1]) for key, value in sorted(totals.items())},
        error_counts_by_category={key: value[0] for key, value in sorted(totals.items())},
    )


OcrCategory = Literal["slide", "board", "no_text"]


class OcrTrial(_StrictModel):
    trial_id: str = Field(min_length=1)
    category: OcrCategory
    reference: str
    hypothesis: str

    @model_validator(mode="after")
    def validate_negative_reference(self) -> OcrTrial:
        if self.category == "no_text" and self.reference:
            raise ValueError("no_text trials must have an empty reference")
        if self.category != "no_text" and not self.reference:
            raise ValueError("text trials need a reference")
        return self


class OcrEvaluation(_StrictModel):
    trial_count_by_category: dict[str, int]
    cer_by_category: dict[str, float]
    no_text_false_positive_rate: float = Field(ge=0.0, le=1.0)
    error_trial_ids: list[str]
    accuracy_claimed: bool


def evaluate_ocr(trials: list[OcrTrial], *, real_model: bool) -> OcrEvaluation:
    categories = {item.category for item in trials}
    if categories != {"slide", "board", "no_text"}:
        raise ValueError("OCR trials must include slide, board, and no_text categories")
    counts: dict[str, int] = defaultdict(int)
    errors: dict[str, int] = defaultdict(int)
    reference_lengths: dict[str, int] = defaultdict(int)
    negative_false_positives = 0
    error_ids: list[str] = []
    for trial in trials:
        counts[trial.category] += 1
        if trial.category == "no_text":
            if trial.hypothesis.strip():
                negative_false_positives += 1
                error_ids.append(trial.trial_id)
            continue
        distance, length = _edit_counts(trial.reference, trial.hypothesis)
        errors[trial.category] += distance
        reference_lengths[trial.category] += length
        if distance:
            error_ids.append(trial.trial_id)
    return OcrEvaluation(
        trial_count_by_category=dict(sorted(counts.items())),
        cer_by_category={
            category: errors[category] / max(1, reference_lengths[category])
            for category in ("board", "slide")
        },
        no_text_false_positive_rate=negative_false_positives / counts["no_text"],
        error_trial_ids=error_ids,
        accuracy_claimed=real_model,
    )


class VisionTrial(_StrictModel):
    trial_id: str = Field(min_length=1)
    truth: dict[str, int]
    prediction: dict[str, int | None]

    @model_validator(mode="after")
    def validate_label_vocabulary(self) -> VisionTrial:
        expected = set(ALLOWED_LABELS)
        if set(self.truth) != expected or set(self.prediction) != expected:
            raise ValueError("vision trials must contain exactly the six allowed labels")
        if any(value < 0 for value in self.truth.values()):
            raise ValueError("vision truth counts cannot be negative")
        if any(value is not None and value < 0 for value in self.prediction.values()):
            raise ValueError("vision prediction counts cannot be negative")
        return self


class VisionEvaluation(_StrictModel):
    trial_count: int = Field(ge=30)
    exact_count_rate_by_label: dict[str, float]
    mean_absolute_error_by_label: dict[str, float]
    unknown_rate_by_label: dict[str, float]
    error_trial_ids: list[str]
    accuracy_claimed: bool


def evaluate_vision(trials: list[VisionTrial], *, real_model: bool) -> VisionEvaluation:
    if len(trials) < 30:
        raise ValueError("at least thirty human-labeled visual trials are required")
    exact: dict[str, int] = defaultdict(int)
    absolute: dict[str, int] = defaultdict(int)
    known: dict[str, int] = defaultdict(int)
    unknown: dict[str, int] = defaultdict(int)
    error_ids: list[str] = []
    for trial in trials:
        trial_has_error = False
        for label in ALLOWED_LABELS:
            predicted = trial.prediction[label]
            if predicted is None:
                unknown[label] += 1
                trial_has_error = True
                continue
            known[label] += 1
            delta = abs(trial.truth[label] - predicted)
            absolute[label] += delta
            exact[label] += int(delta == 0)
            trial_has_error = trial_has_error or delta != 0
        if trial_has_error:
            error_ids.append(trial.trial_id)
    total = len(trials)
    return VisionEvaluation(
        trial_count=total,
        exact_count_rate_by_label={
            label: exact[label] / max(1, known[label]) for label in ALLOWED_LABELS
        },
        mean_absolute_error_by_label={
            label: absolute[label] / max(1, known[label]) for label in ALLOWED_LABELS
        },
        unknown_rate_by_label={label: unknown[label] / total for label in ALLOWED_LABELS},
        error_trial_ids=error_ids,
        accuracy_claimed=real_model,
    )


def _edit_counts(reference: str, hypothesis: str) -> tuple[int, int]:
    expected = _normalize(reference)
    actual = _normalize(hypothesis)
    previous = list(range(len(actual) + 1))
    for row_index, expected_character in enumerate(expected, start=1):
        current = [row_index]
        for column_index, actual_character in enumerate(actual, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column_index] + 1,
                    previous[column_index - 1]
                    + int(expected_character != actual_character),
                )
            )
        previous = current
    return previous[-1], len(expected)


def _normalize(value: str) -> str:
    return "".join(value.lower().split())
