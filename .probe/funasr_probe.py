"""Smoke-probe the local FunASR OpenAI-compatible endpoint with real synthesized Chinese."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from evals.media.run_real_media_eval import _synthesize  # noqa: E402

ROOT = Path(".probe/asr").resolve()
ROOT.mkdir(parents=True, exist_ok=True)

TEXTS = {
    "clean": "同学们好，今天我们学习证据追踪和课堂观察。请只记录可以直接看到和听到的事实。",
    "proper_noun": "灵眸智课 EvidenceClass 使用可追溯证据，不把抽样出现率写成整课时长。",
}

ENDPOINT = "http://127.0.0.1:8000/v1/audio/transcriptions"


def main() -> None:
    for name, text in TEXTS.items():
        wav = ROOT / f"{name}.wav"
        if not wav.is_file():
            _synthesize(text, wav)
        with wave.open(str(wav), "rb") as handle:
            duration = handle.getnframes() / handle.getframerate()
        print(f"--- {name}: {duration:.2f}s, {wav.stat().st_size} bytes")
        with wav.open("rb") as fh:
            response = httpx.post(
                ENDPOINT,
                files={"file": (wav.name, fh, "audio/wav")},
                data={
                    "model": "fun-asr-nano",
                    "response_format": "verbose_json",
                    "language": "中文",
                    "prompt": "灵眸智课,EvidenceClass,证据追踪,课堂观察",
                },
                timeout=900.0,
            )
        print("status", response.status_code)
        body = response.json()
        print("text:", body.get("text"))
        print(
            "timestamp_status:",
            body.get("timestamp_status"),
            "segments:",
            len(body.get("segments") or []),
        )
        print(
            "first segments:",
            json.dumps((body.get("segments") or [])[:2], ensure_ascii=False),
        )


if __name__ == "__main__":
    main()
