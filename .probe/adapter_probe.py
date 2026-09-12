"""Smoke-probe FunAsrHttpAdapter end to end against the live local service."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.model_gateway import FunAsrHttpAdapter  # noqa: E402
from packages.model_gateway.contracts import AsrRequest, InvocationContext  # noqa: E402
from packages.model_gateway.raw_responses import DirectoryRawResponseSink  # noqa: E402

WAV = Path(".probe/asr/clean.wav").resolve()


def main() -> None:
    with FunAsrHttpAdapter(
        base_url="http://127.0.0.1:8000",
        raw_response_sink=DirectoryRawResponseSink(".probe/adapter-raw"),
        hotwords=("灵眸智课", "EvidenceClass", "证据追踪", "课堂观察"),
    ) as adapter:
        print("health:", adapter.health())
        result = adapter.transcribe(
            AsrRequest(
                audio_ref=str(WAV),
                language="zh",
                context=InvocationContext(
                    prompt_version="asr-transcription.v1",
                    config_version="stage5-funasr-smoke.v1",
                    timeout_seconds=600.0,
                    max_output_tokens=16_384,
                ),
            )
        )
    print("provider:", result.metadata.provider)
    print("model:", result.metadata.model, "revision:", result.metadata.model_revision)
    print("latency_ms:", result.metadata.latency_ms)
    print("audio_seconds:", result.metadata.usage.audio_seconds)
    print("request_id:", result.metadata.provider_request_id)
    print("raw_ref:", result.metadata.raw_response_ref)
    print("language:", result.parsed.language)
    print("segments:", len(result.parsed.segments))
    merged = "".join(item.text for item in result.parsed.segments)
    print("text:", merged)
    for item in result.parsed.segments[:3]:
        print(f"  [{item.start_seconds:.2f}-{item.end_seconds:.2f}] {item.text}")


if __name__ == "__main__":
    main()
