"""Opt-in 10-image structured-output smoke evaluation for a real compatible VLM."""

from __future__ import annotations

import argparse
import base64
import json
import os
import struct
import zlib
from collections import Counter
from pathlib import Path

from packages.model_gateway.contracts import InvocationContext, VisionRequest
from packages.model_gateway.errors import ModelGatewayError
from packages.model_gateway.interfaces import VisionModel
from packages.model_gateway.local_qwen import LocalQwen35Adapter
from packages.model_gateway.openai_compatible import OpenAICompatibleAdapter
from packages.model_gateway.raw_responses import DirectoryRawResponseSink


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _synthetic_classroom_png(variant: int, width: int = 128, height: int = 96) -> bytes:
    """Create an original diagram without Pillow, fonts, people, or private media."""

    pixels = [[[245, 245, 245] for _x in range(width)] for _y in range(height)]
    for y in range(8, 30):
        for x in range(52, 76):
            pixels[y][x] = [40, 100, 210]
    student_count = 8 + variant
    for index in range(student_count):
        row, column = divmod(index, 6)
        left, top = 15 + column * 18, 45 + row * 17
        color = [35, 35, 35] if index % 4 else [45, 135, 65]
        for y in range(top, min(top + 8, height)):
            for x in range(left, min(left + 8, width)):
                pixels[y][x] = color
        if index < variant % 4:
            for y in range(max(0, top - 7), top):
                for x in range(left + 2, min(left + 5, width)):
                    pixels[y][x] = [210, 45, 45]
    raw = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in pixels)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(
        b"IDAT", zlib.compress(raw)
    ) + _chunk(b"IEND", b"")


def _data_url(variant: int) -> str:
    encoded = base64.b64encode(_synthetic_classroom_png(variant)).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def run_with_adapter(
    *, adapter: VisionModel, model: str, output_dir: Path, count: int = 10
) -> dict:
    if count != 10:
        raise ValueError("phase-4 acceptance requires exactly 10 self-created images")
    failures: Counter[str] = Counter()
    calls: list[dict] = []
    successes = 0
    for index in range(count):
        context = InvocationContext(
            prompt_version="real-vision-smoke.v0.1",
            config_version="real-vision-low-detail.v0.1",
            timeout_seconds=60.0,
            max_output_tokens=700,
        )
        request = VisionRequest(
            image_refs=[_data_url(index)],
            instruction=(
                "This is a self-created synthetic classroom diagram, not a real person. "
                "Blue marks the teacher and dark or green squares mark student icons. "
                "Red strokes may represent raised-hand markers. Return conservative observable "
                "counts, evidence, limitations, and only the visible region estimates."
            ),
            context=context,
        )
        try:
            result = adapter.observe(request)
        except ModelGatewayError as exc:
            failures[exc.error_code] += 1
            calls.append({"index": index, "status": "failed", "error_code": exc.error_code})
            continue
        successes += 1
        calls.append(
            {
                "index": index,
                "status": "succeeded",
                "provider_request_id": result.metadata.provider_request_id,
                "model_revision": result.metadata.model_revision,
                "latency_ms": result.metadata.latency_ms,
                "input_tokens": result.metadata.usage.input_tokens,
                "output_tokens": result.metadata.usage.output_tokens,
                "cost_usd": result.metadata.usage.cost_usd,
                "raw_response_ref": result.metadata.raw_response_ref,
            }
        )
    report = {
        "schema_version": "real-model-smoke.v0.1",
        "dataset": "10-original-synthetic-classroom-diagrams.v0.1",
        "model": model,
        "total": count,
        "successes": successes,
        "success_rate": successes / count,
        "schema_first_pass_rate": successes / count,
        "failure_classification": dict(sorted(failures.items())),
        "accuracy_claimed": False,
        "calls": calls,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {**report, "report_path": str(report_path.resolve())}


def run(*, model: str, output_dir: Path, count: int = 10) -> dict:
    adapter = OpenAICompatibleAdapter.from_env(
        model=model,
        raw_response_sink=DirectoryRawResponseSink(output_dir / "raw-responses"),
    )
    return run_with_adapter(
        adapter=adapter,
        model=model,
        output_dir=output_dir,
        count=count,
    )


def run_local_qwen(*, model_path: Path, output_dir: Path, count: int = 10) -> dict:
    adapter = LocalQwen35Adapter(
        model_path=model_path,
        raw_response_sink=DirectoryRawResponseSink(output_dir / "raw-responses"),
    )
    return run_with_adapter(
        adapter=adapter,
        model=f"temporary-local:{model_path.name}",
        output_dir=output_dir,
        count=count,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", ""))
    parser.add_argument(
        "--backend",
        choices=("openai-compatible", "local-qwen"),
        default="openai-compatible",
    )
    parser.add_argument("--model-path", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runs/model-gateway-real-vision"),
    )
    args = parser.parse_args()
    if args.backend == "openai-compatible" and not args.model:
        parser.error("--model or OPENAI_MODEL is required; no paid-model default is provided")
    if args.backend == "local-qwen":
        if args.model_path is None:
            parser.error("--model-path is required for local-qwen")
        report = run_local_qwen(model_path=args.model_path, output_dir=args.output)
    else:
        report = run(model=args.model, output_dir=args.output)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
