"""Optional local RapidOCR adapter; model bytes stay outside SQL and Git."""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter
from typing import Any

from .contracts import (
    InvocationMetadata,
    ModelUsage,
    OcrBox,
    OcrItem,
    OcrOutput,
    OcrRequest,
    OcrResult,
)
from .raw_responses import RawResponseSink


class RapidOcrAdapter:
    provider = "rapidocr-local"

    def __init__(
        self,
        *,
        raw_response_sink: RawResponseSink,
        engine: Any | None = None,
        image_size_loader: Callable[[Path], tuple[int, int]] | None = None,
    ) -> None:
        self._raw_sink = raw_response_sink
        if engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:
                raise RuntimeError("install the media-models optional dependency") from exc
            engine = RapidOCR()
        self._engine = engine
        self._image_size_loader = image_size_loader

    def recognize(self, request: OcrRequest) -> OcrResult:
        image_size_loader = self._image_size_loader or _pillow_image_size
        started = perf_counter()
        items: list[OcrItem] = []
        raw_audit: list[dict[str, object]] = []
        for image_ref in request.image_refs:
            image_path = _local_path(image_ref)
            width, height = image_size_loader(image_path)
            raw_result = self._engine(str(image_path))
            rows = raw_result[0] if isinstance(raw_result, tuple) else raw_result
            for row in rows or []:
                box_points, text, confidence = row[:3]
                xs = [float(point[0]) for point in box_points]
                ys = [float(point[1]) for point in box_points]
                x1, x2 = max(0.0, min(xs)), min(float(width), max(xs))
                y1, y2 = max(0.0, min(ys)), min(float(height), max(ys))
                normalized = OcrBox(
                    x=x1 / width,
                    y=y1 / height,
                    width=max(1 / width, (x2 - x1) / width),
                    height=max(1 / height, (y2 - y1) / height),
                )
                item = OcrItem(
                    image_ref=image_ref,
                    text=str(text).strip(),
                    confidence=float(confidence),
                    box=normalized,
                )
                if item.text:
                    items.append(item)
                    raw_audit.append(item.model_dump(mode="json"))
        raw_ref = self._raw_sink.put(json.dumps(raw_audit, ensure_ascii=False).encode("utf-8"))
        parsed = OcrOutput(items=items)
        return OcrResult(
            metadata=InvocationMetadata(
                provider=self.provider,
                model="rapidocr-onnxruntime",
                model_revision=_package_version(),
                prompt_version=request.context.prompt_version,
                config_version=request.context.config_version,
                latency_ms=round((perf_counter() - started) * 1000, 3),
                usage=ModelUsage(characters=sum(len(item.text) for item in items), cost_usd=0.0),
                raw_response_ref=raw_ref,
                provider_request_id=None,
            ),
            parsed=parsed,
        )


def _local_path(image_ref: str) -> Path:
    if image_ref.startswith("file:"):
        from urllib.parse import unquote, urlparse

        parsed = urlparse(image_ref)
        value = unquote(parsed.path)
        if parsed.netloc:
            value = f"//{parsed.netloc}{value}"
        if len(value) >= 3 and value[0] == "/" and value[2] == ":":
            value = value[1:]
        return Path(value).resolve(strict=True)
    return Path(image_ref).resolve(strict=True)


def _package_version() -> str:
    try:
        return version("rapidocr-onnxruntime")
    except PackageNotFoundError:
        return "injected-test-engine"


def _pillow_image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required by the RapidOCR adapter") from exc
    with Image.open(path) as image:
        return image.size
