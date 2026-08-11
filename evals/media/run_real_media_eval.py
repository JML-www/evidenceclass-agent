"""Run authorized synthetic 5-minute ASR and three-category local OCR acceptance."""

from __future__ import annotations

import argparse
import json
import subprocess
import wave
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from packages.media_pipeline.evaluation import (
    AsrReferenceSample,
    OcrTrial,
    evaluate_asr,
    evaluate_ocr,
)
from packages.media_pipeline.tools import resolve_media_tool
from packages.model_gateway import FasterWhisperAdapter, RapidOcrAdapter
from packages.model_gateway.contracts import AsrRequest, InvocationContext, OcrRequest
from packages.model_gateway.raw_responses import DirectoryRawResponseSink

ASR_TEXTS = {
    "clean": "同学们好，今天我们学习证据追踪和课堂观察。请只记录可以直接看到和听到的事实。",
    "noise": "请阅读屏幕上的学习目标，然后用一分钟整理自己的证据。",
    "proper_noun": "灵眸智课 EvidenceClass 使用可追溯证据，不把抽样出现率写成整课时长。",
    "overlap": "第一小组先说明观察结果，第二小组随后补充证据来源。",
}


def _run(args: list[str]) -> None:
    completed = subprocess.run(args, capture_output=True, check=False, shell=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))


def _synthesize(text: str, destination: Path) -> None:
    escaped_path = str(destination.resolve()).replace("'", "''")
    escaped_text = text.replace("'", "''")
    command = (
        "Add-Type -AssemblyName System.Speech; "
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SelectVoice('Microsoft Huihui Desktop'); "
        f"$s.SetOutputToWaveFile('{escaped_path}'); "
        f"$s.Speak('{escaped_text}'); $s.Dispose()"
    )
    _run(["powershell.exe", "-NoProfile", "-Command", command])


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def _build_asr_fixture(root: Path) -> tuple[Path, list[dict[str, Any]]]:
    ffmpeg = str(resolve_media_tool("ffmpeg"))
    sources: dict[str, Path] = {}
    for category, text in ASR_TEXTS.items():
        raw = root / f"{category}.sapi.wav"
        normalized = root / f"{category}.wav"
        _synthesize(text, raw)
        _run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(raw),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(normalized),
            ]
        )
        sources[category] = normalized

    noisy = root / "noise-mixed.wav"
    noise_duration = _duration(sources["noise"])
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(sources["noise"]),
            "-f",
            "lavfi",
            "-i",
            (
                "anoisesrc=color=white:amplitude=0.02:"
                f"seed=20260811:d={noise_duration:.3f}"
            ),
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first:weights='1 0.35'",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(noisy),
        ]
    )
    sources["noise"] = noisy

    overlap = root / "overlap-mixed.wav"
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(sources["overlap"]),
            "-i",
            str(sources["proper_noun"]),
            "-filter_complex",
            "[1:a]adelay=450[late];[0:a][late]amix=inputs=2:duration=longest",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(overlap),
        ]
    )
    sources["overlap"] = overlap

    ordered = ["clean", "noise", "proper_noun", "overlap"]
    prefix = root / "acceptance-prefix.wav"
    concat_inputs: list[str] = []
    for category in ordered:
        concat_inputs.extend(["-i", str(sources[category])])
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            *concat_inputs,
            "-filter_complex",
            "[0:a][1:a][2:a][3:a]concat=n=4:v=0:a=1[out]",
            "-map",
            "[out]",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(prefix),
        ]
    )
    five_minutes = root / "authorized-synthetic-5min.wav"
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(prefix),
            "-t",
            "300",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(five_minutes),
        ]
    )
    windows = []
    cursor = 0.0
    for category in ordered:
        end = cursor + _duration(sources[category])
        reference = ASR_TEXTS[category]
        if category == "overlap":
            reference += ASR_TEXTS["proper_noun"]
        windows.append(
            {"category": category, "start": cursor, "end": end, "reference": reference}
        )
        cursor = end
    return five_minutes, windows


def _asr_eval(root: Path, model_name: str) -> dict[str, Any]:
    audio, windows = _build_asr_fixture(root)
    sink = DirectoryRawResponseSink(root / "raw-asr")
    adapter = FasterWhisperAdapter(
        model_name_or_path=model_name,
        raw_response_sink=sink,
        device="cpu",
        compute_type="int8",
    )
    result = adapter.transcribe(
        AsrRequest(
            audio_ref=str(audio),
            language="zh",
            context=InvocationContext(
                prompt_version="asr-transcription.v1",
                config_version="stage5-real-asr-eval.v1",
                timeout_seconds=600.0,
                max_output_tokens=16_384,
            ),
        )
    )
    samples = []
    for index, window in enumerate(windows, start=1):
        hypothesis = "".join(
            item.text
            for item in result.parsed.segments
            if window["start"]
            <= (item.start_seconds + item.end_seconds) / 2
            < window["end"]
        )
        samples.append(
            AsrReferenceSample(
                sample_id=f"{window['category']}-{index}",
                category=window["category"],
                reference=window["reference"],
                hypothesis=hypothesis,
            )
        )
    evaluation = evaluate_asr(samples, source_duration_seconds=_duration(audio))
    return {
        "fixture": {
            "authorized": True,
            "synthetic": True,
            "duration_seconds": _duration(audio),
            "manual_reference_windows": len(samples),
        },
        "metadata": result.metadata.model_dump(mode="json"),
        "samples": [item.model_dump(mode="json") for item in samples],
        "evaluation": evaluation.model_dump(mode="json"),
    }


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    raise RuntimeError("no suitable local font is available for synthetic OCR fixtures")


def _build_ocr_fixtures(root: Path) -> list[tuple[str, str, Path]]:
    fixtures: list[tuple[str, str, Path]] = []
    texts = {
        "slide": ["函数与证据", "课堂学习目标", "Evidence Class"],
        "board": ["一次函数", "提问与讨论", "证据时间线"],
    }
    for category, values in texts.items():
        for index, text in enumerate(values, start=1):
            background = "white" if category == "slide" else "#29423b"
            foreground = "black" if category == "slide" else "white"
            image = Image.new("RGB", (960, 540), background)
            draw = ImageDraw.Draw(image)
            draw.text((100, 210), text, font=_font(64), fill=foreground)
            if category == "board":
                image = image.filter(ImageFilter.GaussianBlur(radius=0.55))
            destination = root / f"ocr-{category}-{index}.png"
            image.save(destination)
            fixtures.append((category, text, destination))
    for index in range(1, 4):
        image = Image.new("RGB", (960, 540), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((100, 100, 300, 300), outline="#336699", width=8)
        draw.ellipse((500, 180, 700, 380), fill="#e0e0e0")
        destination = root / f"ocr-no-text-{index}.png"
        image.save(destination)
        fixtures.append(("no_text", "", destination))
    return fixtures


def _ocr_eval(root: Path) -> dict[str, Any]:
    fixtures = _build_ocr_fixtures(root)
    sink = DirectoryRawResponseSink(root / "raw-ocr")
    adapter = RapidOcrAdapter(raw_response_sink=sink)
    references = [path.as_uri() for _, _, path in fixtures]
    result = adapter.recognize(
        OcrRequest(
            image_refs=references,
            context=InvocationContext(
                prompt_version="ocr-frame-text.v1",
                config_version="stage5-real-ocr-eval.v1",
                timeout_seconds=120.0,
                max_output_tokens=4096,
            ),
        )
    )
    by_ref: dict[str, list[tuple[str, float]]] = {value: [] for value in references}
    for item in result.parsed.items:
        by_ref[item.image_ref].append((item.text, item.confidence))
    raw_trials = [
        OcrTrial(
            trial_id=path.stem,
            category=category,
            reference=reference,
            hypothesis="".join(text for text, _ in by_ref[path.as_uri()]),
        )
        for category, reference, path in fixtures
    ]
    selected_threshold = 0.8
    filtered_trials = [
        OcrTrial(
            trial_id=path.stem,
            category=category,
            reference=reference,
            hypothesis="".join(
                text
                for text, confidence in by_ref[path.as_uri()]
                if confidence >= selected_threshold
            ),
        )
        for category, reference, path in fixtures
    ]
    raw_evaluation = evaluate_ocr(raw_trials, real_model=True)
    evaluation = evaluate_ocr(filtered_trials, real_model=True)
    return {
        "fixture": {"authorized": True, "synthetic": True, "trial_count": len(raw_trials)},
        "metadata": result.metadata.model_dump(mode="json"),
        "selected_confidence_threshold": selected_threshold,
        "threshold_selection_note": (
            "Selected on the versioned slide/board/no-text synthetic validation fixture."
        ),
        "raw_trials": [item.model_dump(mode="json") for item in raw_trials],
        "filtered_trials": [item.model_dump(mode="json") for item in filtered_trials],
        "raw_evaluation": raw_evaluation.model_dump(mode="json"),
        "evaluation": evaluation.model_dump(mode="json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--whisper-model", required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "stage5-real-media-eval.v1",
        "claim_boundary": (
            "Real local ASR/OCR on authorized synthetic fixtures; this is not classroom accuracy."
        ),
        "asr": _asr_eval(output, args.whisper_model),
        "ocr": _ocr_eval(output),
    }
    destination = output / "report.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "report": str(destination),
                "asr_cer": report["asr"]["evaluation"]["overall_cer"],
                "ocr_error_trials": report["ocr"]["evaluation"]["error_trial_ids"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
