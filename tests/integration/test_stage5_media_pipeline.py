from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from packages.media_pipeline.audio import AudioExtractor, EnergyVadChunker
from packages.media_pipeline.errors import (
    CorruptMediaError,
    MediaLimitExceededError,
    UnsafeMediaPathError,
)
from packages.media_pipeline.evaluation import VisionTrial, evaluate_vision
from packages.media_pipeline.pipeline import Stage5MediaPipeline
from packages.media_pipeline.probe import ProbePolicy, SafeMediaProbe
from packages.media_pipeline.sampling import (
    LocalFrameSink,
    ReproducibleFrameSampler,
    SamplingPolicy,
)
from packages.media_pipeline.tools import resolve_media_tool
from packages.model_gateway import FakeModelGateway
from scripts.generate_stage5_trials import generate as generate_visual_trials


@dataclass(frozen=True)
class MediaFixtures:
    root: Path
    normal: Path
    no_audio: Path
    corrupt: Path
    disguised_text: Path
    huge_metadata: Path


def _run(args: list[str]) -> None:
    completed = subprocess.run(args, capture_output=True, check=False, shell=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))


@pytest.fixture(scope="module")
def media_fixtures(tmp_path_factory: pytest.TempPathFactory) -> MediaFixtures:
    root = tmp_path_factory.mktemp("阶段五 中文 空格")
    ffmpeg = str(resolve_media_tool("ffmpeg"))
    normal = root / "正常 十秒.mp4"
    no_audio = root / "无音轨 视频.mp4"
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=10:duration=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=16000:duration=10",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(normal),
        ]
    )
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:r=10:d=10",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(no_audio),
        ]
    )
    huge_metadata = root / "超大元数据.mp4"
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(normal),
            "-map",
            "0",
            "-c",
            "copy",
            "-metadata",
            "comment=" + ("M" * 2048),
            str(huge_metadata),
        ]
    )
    corrupt = root / "损坏 视频.mp4"
    data = normal.read_bytes()
    corrupt.write_bytes(data[: max(256, len(data) // 5)])
    disguised = root / "文本伪装.mp4"
    disguised.write_text("this is plain text, not media", encoding="utf-8")
    return MediaFixtures(root, normal, no_audio, corrupt, disguised, huge_metadata)


def test_safe_probe_accepts_ten_seconds_no_audio_and_unicode_space_paths(media_fixtures):
    probe = SafeMediaProbe()

    normal = probe.inspect(media_fixtures.normal, allowed_root=media_fixtures.root)
    no_audio = probe.inspect(media_fixtures.no_audio, allowed_root=media_fixtures.root)

    assert normal.duration_ms == pytest.approx(10_000, abs=100)
    assert normal.video.width == 320
    assert normal.video.codec == "h264"
    assert len(normal.audio_streams) == 1
    assert no_audio.audio_streams == []


def test_safe_probe_rejects_corrupt_text_disguise_and_limits(media_fixtures):
    probe = SafeMediaProbe()
    with pytest.raises(CorruptMediaError):
        probe.inspect(media_fixtures.corrupt)
    with pytest.raises(CorruptMediaError):
        probe.inspect(media_fixtures.disguised_text)
    with pytest.raises(MediaLimitExceededError, match="metadata"):
        SafeMediaProbe(policy=ProbePolicy(max_metadata_bytes=256)).inspect(
            media_fixtures.huge_metadata
        )
    with pytest.raises(MediaLimitExceededError, match="duration"):
        SafeMediaProbe(policy=ProbePolicy(max_duration_seconds=5.0)).inspect(
            media_fixtures.normal
        )
    with pytest.raises(MediaLimitExceededError, match="dimensions"):
        SafeMediaProbe(policy=ProbePolicy(max_width=100)).inspect(media_fixtures.normal)
    with pytest.raises(MediaLimitExceededError, match="size"):
        SafeMediaProbe(policy=ProbePolicy(max_file_bytes=1)).inspect(media_fixtures.normal)
    with pytest.raises(UnsafeMediaPathError):
        probe.inspect("https://example.invalid/video.mp4")


def test_repeated_sampling_has_identical_times_hashes_and_global_camera_offsets(
    media_fixtures, tmp_path
):
    media = SafeMediaProbe().inspect(media_fixtures.normal)
    sampler = ReproducibleFrameSampler(sink=LocalFrameSink(tmp_path / "frames"))
    policy = SamplingPolicy(mode="uniform", sample_count=4)

    first = sampler.sample(
        media_fixtures.normal,
        probe=media,
        asset_id="asset-a",
        camera_id="front",
        global_offset_ms=5000,
        policy=policy,
    )
    repeated = sampler.sample(
        media_fixtures.normal,
        probe=media,
        asset_id="asset-a",
        camera_id="front",
        global_offset_ms=5000,
        policy=policy,
    )
    second_camera = sampler.sample(
        media_fixtures.normal,
        probe=media,
        asset_id="asset-b",
        camera_id="back",
        global_offset_ms=5000,
        policy=policy,
    )

    assert [(item.local_timestamp_ms, item.sha256) for item in first] == [
        (item.local_timestamp_ms, item.sha256) for item in repeated
    ]
    assert [item.global_timestamp_ms for item in first] == [
        item.global_timestamp_ms for item in second_camera
    ]
    assert all(item.global_timestamp_ms == item.local_timestamp_ms + 5000 for item in first)


def test_optional_scene_change_sampling_is_bounded_and_reproducible(media_fixtures, tmp_path):
    media = SafeMediaProbe().inspect(media_fixtures.normal)
    sampler = ReproducibleFrameSampler(sink=LocalFrameSink(tmp_path / "scenes"))
    policy = SamplingPolicy(mode="scene_change", scene_threshold=0.1, max_scene_frames=3)

    first = sampler.sample(
        media_fixtures.normal,
        probe=media,
        asset_id="scene-asset",
        camera_id="front",
        policy=policy,
    )
    second = sampler.sample(
        media_fixtures.normal,
        probe=media,
        asset_id="scene-asset",
        camera_id="front",
        policy=policy,
    )

    assert 1 <= len(first) <= 3
    assert [(item.global_timestamp_ms, item.sha256) for item in first] == [
        (item.global_timestamp_ms, item.sha256) for item in second
    ]


def test_complete_real_media_fake_model_pipeline_is_offline_and_traceable(
    media_fixtures, tmp_path, monkeypatch
):
    def forbid_socket(*args, **kwargs):
        raise AssertionError("offline stage-5 acceptance attempted network access")

    monkeypatch.setattr("socket.create_connection", forbid_socket)
    gateway = FakeModelGateway()
    pipeline = Stage5MediaPipeline(
        probe=SafeMediaProbe(),
        sampler=ReproducibleFrameSampler(sink=LocalFrameSink(tmp_path / "objects")),
        audio_extractor=AudioExtractor(output_root=tmp_path / "audio"),
        vad_chunker=EnergyVadChunker(output_root=tmp_path / "chunks"),
        asr_model=gateway,
        ocr_model=gateway,
        vision_model=gateway,
        ocr_confidence_threshold=0.8,
        ocr_threshold_selection_note="Synthetic slide/board/no-text trial set v1.",
    )

    result = pipeline.run(
        media_fixtures.normal,
        asset_id="asset-stage5",
        camera_id="front-camera",
        allowed_root=media_fixtures.root,
        sampling_policy=SamplingPolicy(sample_count=3),
    )

    assert len(result.frames) == 3
    assert result.transcript is not None
    assert result.transcript.speaker_role_metrics_available is False
    assert result.ocr is not None and result.ocr.items
    assert len(result.visual_observations) == 3
    assert result.unavailable_outputs == []
    assert {capability for capability, _ in gateway.calls} == {"asr", "ocr", "vision"}


def test_no_audio_is_an_explicit_capability_result_not_a_failure(media_fixtures, tmp_path):
    gateway = FakeModelGateway()
    pipeline = Stage5MediaPipeline(
        probe=SafeMediaProbe(),
        sampler=ReproducibleFrameSampler(sink=LocalFrameSink(tmp_path / "objects")),
        audio_extractor=AudioExtractor(output_root=tmp_path / "audio"),
        vad_chunker=EnergyVadChunker(output_root=tmp_path / "chunks"),
        asr_model=gateway,
    )

    result = pipeline.run(
        media_fixtures.no_audio,
        asset_id="asset-no-audio",
        camera_id="front",
        sampling_policy=SamplingPolicy(sample_count=1),
    )

    assert result.transcript is None
    assert "asr:no_audio_track" in result.unavailable_outputs


def test_thirty_rendered_trial_images_have_versioned_truth_and_fake_claim_boundary(tmp_path):
    report = generate_visual_trials(tmp_path / "visual-trials")
    gateway = FakeModelGateway()
    trials = []
    for index, item in enumerate(report["trials"]):
        frame = {
            "frame_id": item["trial_id"],
            "asset_id": "synthetic-visual-trials-v1",
            "camera_id": "synthetic",
            "local_timestamp_ms": index * 1000,
            "global_timestamp_ms": index * 1000,
            "sha256": item["sha256"],
            "object_ref": Path(item["image"]).as_uri(),
            "sampling_policy_version": "synthetic-trial-render.v1",
        }
        from packages.media_pipeline.sampling import SampledFrame
        from packages.media_pipeline.vision import LimitedFrameObserver

        observation = LimitedFrameObserver(gateway).observe(SampledFrame(**frame))
        prediction = {entry.label: entry.count for entry in observation.inference.labels}
        trials.append(
            VisionTrial(
                trial_id=item["trial_id"],
                truth=item["truth"],
                prediction=prediction,
            )
        )

    evaluation = evaluate_vision(trials, real_model=False)

    assert report["trial_count"] == 30
    assert evaluation.trial_count == 30
    assert evaluation.accuracy_claimed is False
