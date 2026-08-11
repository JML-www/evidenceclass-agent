from copy import deepcopy

import pytest
from pydantic import ValidationError

from packages.media_pipeline.audio import AsrPipeline, SpeechChunk
from packages.media_pipeline.evaluation import (
    AsrReferenceSample,
    OcrTrial,
    VisionTrial,
    evaluate_asr,
    evaluate_ocr,
    evaluate_vision,
)
from packages.media_pipeline.ocr import OcrPipeline
from packages.media_pipeline.sampling import SampledFrame, uniform_timestamps
from packages.media_pipeline.segments import (
    LocalEvidenceSpan,
    SegmentManifest,
    SegmentObservation,
    SegmentSpec,
    merge_segment_observations,
)
from packages.media_pipeline.vision import (
    ALLOWED_LABELS,
    LimitedFrameObserver,
    LimitedVisionInference,
)
from packages.model_gateway import FakeModelGateway


def _frame() -> SampledFrame:
    return SampledFrame(
        frame_id="frame-001",
        asset_id="asset-001",
        camera_id="front-camera",
        local_timestamp_ms=1000,
        global_timestamp_ms=6000,
        sha256="a" * 64,
        object_ref="fixture://frame/001",
        sampling_policy_version="frame-sampling.v1",
    )


def test_uniform_sampling_uses_stable_center_of_bin_milliseconds():
    first = uniform_timestamps(10_000, 4)
    second = uniform_timestamps(10_000, 4)

    assert first == [1250, 3750, 6250, 8750]
    assert second == first


def test_asr_merge_globalizes_time_without_inventing_speaker_roles():
    document = AsrPipeline(FakeModelGateway()).transcribe(
        [
            SpeechChunk(
                chunk_id="chunk-1",
                audio_ref="fixture://audio/chunk-1",
                start_ms=2000,
                end_ms=7000,
            )
        ],
        language="zh",
        global_offset_ms=10_000,
    )

    assert document.segments[0].start_ms == 12_000
    assert document.segments[0].speaker_role == "unknown"
    assert document.speaker_diarization is False
    assert document.speaker_role_metrics_available is False


def test_ocr_retains_raw_low_confidence_text_and_marks_filtering_explicitly():
    result = OcrPipeline(
        FakeModelGateway(),
        confidence_threshold=0.995,
        threshold_selection_note="Selected on synthetic slide, board, and negative trials v1.",
    ).recognize([_frame()])

    assert len(result.items) == 1
    assert result.items[0].raw_text == "Synthetic lesson"
    assert result.items[0].filtered_text is None
    assert result.all_below_threshold is True


def test_limited_vision_uses_only_six_labels_and_system_owned_time():
    observation = LimitedFrameObserver(FakeModelGateway()).observe(_frame())

    assert {item.label for item in observation.inference.labels} == set(ALLOWED_LABELS)
    assert observation.global_timestamp_ms == 6000
    assert observation.frame_id == "frame-001"


def test_limited_vision_rejects_count_above_visible_people():
    raw = FakeModelGateway()._fixture["limited_vision"]  # versioned test fixture
    invalid = deepcopy(raw)
    invalid["visible_person_count"] = 1

    with pytest.raises(ValidationError, match="visible_person_count"):
        LimitedVisionInference.model_validate(invalid)


def test_segment_merge_sorts_deduplicates_and_globalizes_evidence():
    manifest = SegmentManifest(
        asset_id="asset-long",
        camera_id="front",
        total_duration_ms=3000,
        segments=[
            SegmentSpec(
                segment_id="s1",
                index=1,
                global_offset_ms=0,
                duration_ms=1000,
                source_sha256="a" * 64,
            ),
            SegmentSpec(
                segment_id="s2",
                index=2,
                global_offset_ms=1000,
                duration_ms=2000,
                source_sha256="b" * 64,
            ),
        ],
    )
    first = SegmentObservation(
        segment_id="s1",
        index=1,
        label_counts={"raise_hand": 1},
        duration_metrics_ms={"teacher_at_podium": 500},
        weighted_metrics={"visible_ratio": 1.0},
        evidence=[
            LocalEvidenceSpan(
                evidence_id="e1", fact="one raised hand", local_start_ms=100, local_end_ms=200
            )
        ],
    )
    second = SegmentObservation(
        segment_id="s2",
        index=2,
        label_counts={"raise_hand": 2},
        duration_metrics_ms={"teacher_at_podium": 250},
        weighted_metrics={"visible_ratio": 0.25},
        evidence=[
            LocalEvidenceSpan(
                evidence_id="e2", fact="two raised hands", local_start_ms=100, local_end_ms=300
            )
        ],
    )

    merged = merge_segment_observations(manifest, [second, first, second])
    repeated = merge_segment_observations(manifest, [first, second])

    assert merged.ordered_segment_ids == ["s1", "s2"]
    assert merged.duplicate_inputs_ignored == 1
    assert merged.label_counts["raise_hand"] == 3
    assert merged.duration_metrics_ms["teacher_at_podium"] == 750
    assert merged.weighted_metrics["visible_ratio"] == pytest.approx(0.5)
    assert merged.evidence[1].global_start_ms == 1100
    assert merged.merge_id == repeated.merge_id


def test_segment_merge_reports_missing_and_conflicting_duplicate_segments():
    manifest = SegmentManifest(
        asset_id="asset",
        camera_id="camera",
        total_duration_ms=2000,
        segments=[
            SegmentSpec(
                segment_id="s1",
                index=1,
                global_offset_ms=0,
                duration_ms=1000,
                source_sha256="a" * 64,
            ),
            SegmentSpec(
                segment_id="s2",
                index=2,
                global_offset_ms=1000,
                duration_ms=1000,
                source_sha256="b" * 64,
            ),
        ],
    )
    first = SegmentObservation(segment_id="s1", index=1, label_counts={"standing": 1})

    with pytest.raises(RuntimeError, match="incomplete"):
        merge_segment_observations(manifest, [first])
    with pytest.raises(RuntimeError, match="conflicting duplicate"):
        merge_segment_observations(
            manifest,
            [
                first,
                SegmentObservation(segment_id="s1", index=1, label_counts={"standing": 2}),
            ],
        )


def test_asr_ocr_and_thirty_image_evaluators_preserve_claim_boundaries():
    asr = evaluate_asr(
        [
            AsrReferenceSample(
                sample_id="noise-1", category="noise", reference="课堂观察", hypothesis="课堂关察"
            ),
            AsrReferenceSample(
                sample_id="term-1",
                category="proper_noun",
                reference="灵眸智课",
                hypothesis="灵眸智课",
            ),
            AsrReferenceSample(
                sample_id="overlap-1",
                category="overlap",
                reference="请开始讨论",
                hypothesis="开始讨论",
            ),
        ],
        source_duration_seconds=300.0,
    )
    ocr = evaluate_ocr(
        [
            OcrTrial(trial_id="slide", category="slide", reference="函数", hypothesis="函教"),
            OcrTrial(trial_id="board", category="board", reference="证据", hypothesis="证据"),
            OcrTrial(trial_id="negative", category="no_text", reference="", hypothesis="noise"),
        ],
        real_model=False,
    )
    truth = {label: 0 for label in ALLOWED_LABELS}
    vision = evaluate_vision(
        [
            VisionTrial(
                trial_id=f"trial-{index:02d}",
                truth=truth,
                prediction={label: 0 for label in ALLOWED_LABELS},
            )
            for index in range(30)
        ],
        real_model=False,
    )

    assert asr.overall_cer > 0
    assert asr.accuracy_claimed is False
    assert ocr.no_text_false_positive_rate == 1.0
    assert ocr.accuracy_claimed is False
    assert vision.trial_count == 30
    assert vision.accuracy_claimed is False
