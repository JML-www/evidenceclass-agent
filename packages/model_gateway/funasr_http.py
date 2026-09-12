"""Local FunASR adapter that speaks the OpenAI-compatible transcription HTTP contract.

The bundled FunASR service (Fun-ASR-Nano-2512) exposes ``POST /v1/audio/transcriptions``
with an OpenAI-shaped multipart request. This adapter keeps the phase-4 ``AsrModel``
Protocol so the rest of the system cannot tell a remote provider from this local one.
"""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from .contracts import (
    AsrOutput,
    AsrRequest,
    AsrResult,
    AsrSegment,
    InvocationMetadata,
    ModelUsage,
)
from .errors import (
    DeterministicModelRequestError,
    ModelAuthenticationError,
    ModelPermissionDeniedError,
    ModelRateLimitError,
    ModelServerError,
    ModelTimeoutError,
    SchemaParseError,
)
from .raw_responses import RawResponseSink

# The local service accepts human language names rather than BCP-47 codes.
_LANGUAGE_ALIASES = {
    "zh": "中文",
    "zh-cn": "中文",
    "zh-hans": "中文",
    "cmn": "中文",
    "en": "English",
    "en-us": "English",
    "yue": "粤语",
    "ja": "日本語",
    "ko": "한국어",
}
_LANGUAGE_CODES = {value: key for key, value in _LANGUAGE_ALIASES.items()}
_LANGUAGE_CODES.update({"中文": "zh", "English": "en", "粤语": "yue", "日本語": "ja", "한국어": "ko"})


class FunAsrHttpAdapter:
    """Transcribe through a locally hosted FunASR OpenAI-compatible endpoint."""

    provider = "funasr-http-local"

    def __init__(
        self,
        *,
        base_url: str,
        raw_response_sink: RawResponseSink,
        model_alias: str = "fun-asr-nano",
        hotwords: tuple[str, ...] = (),
        default_language: str = "zh",
        http_client: httpx.Client | None = None,
    ) -> None:
        normalized = base_url.strip().rstrip("/")
        if not normalized:
            raise ValueError("a FunASR base URL such as http://127.0.0.1:8000 is required")
        if not model_alias.strip():
            raise ValueError("a FunASR model alias is required")
        self._endpoint = f"{normalized}/v1/audio/transcriptions"
        self._health_endpoint = f"{normalized}/health"
        self._model_alias = model_alias
        self._hotwords = tuple(item.strip() for item in hotwords if item.strip())
        self._default_language = default_language
        self._raw_sink = raw_response_sink
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> FunAsrHttpAdapter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        """Return the service readiness payload; raises when the service is unreachable."""
        try:
            response = self._client.get(self._health_endpoint, timeout=10.0)
        except httpx.HTTPError as exc:  # pragma: no cover - depends on a live service
            raise ModelServerError(f"FunASR health probe failed: {exc}") from exc
        if response.status_code >= 500:
            raise ModelServerError(f"FunASR service is not ready ({response.status_code})")
        return dict(response.json())

    def transcribe(self, request: AsrRequest) -> AsrResult:
        audio = Path(request.audio_ref).resolve(strict=True)
        language = request.language or self._default_language
        started = perf_counter()
        payload = self._post(audio, language, request.context.timeout_seconds)
        latency_ms = round((perf_counter() - started) * 1000, 3)

        body = _decode_body(payload)
        raw_ref = self._raw_sink.put(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        duration = _media_duration(audio)
        parsed = _to_output(body, request.language, duration)
        return AsrResult(
            metadata=InvocationMetadata(
                provider=self.provider,
                model=self._model_alias,
                model_revision=str(body.get("model") or self._model_alias),
                prompt_version=request.context.prompt_version,
                config_version=request.context.config_version,
                latency_ms=latency_ms,
                usage=ModelUsage(audio_seconds=duration, cost_usd=0.0),
                raw_response_ref=raw_ref,
                provider_request_id=_optional_str(body.get("request_id")),
            ),
            parsed=parsed,
        )

    def _post(self, audio: Path, language: str, timeout_seconds: float) -> bytes:
        data: dict[str, str] = {
            "model": self._model_alias,
            "response_format": "verbose_json",
            "language": _LANGUAGE_ALIASES.get(language.lower(), language),
        }
        if self._hotwords:
            data["prompt"] = ",".join(self._hotwords)
        try:
            with audio.open("rb") as handle:
                response = self._client.post(
                    self._endpoint,
                    files={"file": (audio.name, handle, "application/octet-stream")},
                    data=data,
                    timeout=timeout_seconds,
                )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError("FunASR transcription timed out") from exc
        except httpx.HTTPError as exc:
            raise ModelServerError(f"FunASR connection failed: {exc}") from exc
        _raise_for_status(response)
        return response.content


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    detail = _error_detail(response)
    if response.status_code == 401:
        raise ModelAuthenticationError(f"FunASR rejected the credentials: {detail}")
    if response.status_code == 403:
        raise ModelPermissionDeniedError(f"FunASR denied the request: {detail}")
    if response.status_code == 429:
        raise ModelRateLimitError(f"FunASR is busy: {detail}")
    if response.status_code >= 500:
        raise ModelServerError(f"FunASR returned {response.status_code}: {detail}")
    raise DeterministicModelRequestError(f"FunASR rejected the request: {detail}")


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:400]
    if isinstance(body, dict):
        return str(body.get("detail") or body.get("message") or body)[:400]
    return str(body)[:400]


def _decode_body(payload: bytes) -> dict[str, Any]:
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SchemaParseError("FunASR returned a non-JSON transcription body") from exc
    if not isinstance(body, dict):
        raise SchemaParseError("FunASR returned a transcription body that is not an object")
    return body


def _to_output(body: dict[str, Any], requested_language: str, duration: float) -> AsrOutput:
    segments = [
        AsrSegment(
            start_seconds=max(0.0, float(item["start"])),
            end_seconds=max(0.0, float(item["end"])),
            text=str(item["text"]).strip(),
        )
        for item in _valid_segments(body.get("segments"))
    ]
    if not segments:
        text = str(body.get("text") or "").strip()
        if text:
            segments = [
                AsrSegment(start_seconds=0.0, end_seconds=max(0.0, duration), text=text)
            ]
    if not segments:
        raise SchemaParseError("FunASR returned neither timestamped segments nor transcript text")
    echo = str(body.get("language") or "")
    language = _LANGUAGE_CODES.get(echo) or requested_language
    return AsrOutput(language=language, segments=segments)


def _valid_segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    accepted: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        start = item.get("start")
        end = item.get("end")
        if not text or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        if float(end) <= float(start):
            continue
        accepted.append({"start": float(start), "end": float(end), "text": text})
    return accepted


def _optional_str(value: Any) -> str | None:
    return str(value) if value else None


def _media_duration(path: Path) -> float:
    """Best-effort duration in seconds; unknown duration degrades to 0.0 rather than guessing."""
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as handle:
                return handle.getnframes() / handle.getframerate()
        except (wave.Error, ZeroDivisionError, OSError):
            pass
    return _probe_duration(path)


def _probe_duration(path: Path) -> float:
    try:
        from packages.media_pipeline.tools import resolve_media_tool
    except ImportError:  # pragma: no cover - the media pipeline is optional here
        return 0.0
    try:
        ffprobe = resolve_media_tool("ffprobe")
    except (RuntimeError, FileNotFoundError):
        return 0.0
    completed = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        return 0.0
    try:
        return max(0.0, float(completed.stdout.strip()))
    except ValueError:
        return 0.0
