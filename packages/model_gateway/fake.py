"""Deterministic all-capability adapter for offline CI and fault injection."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .contracts import (
    AsrOutput,
    AsrRequest,
    AsrResult,
    ChatOutput,
    ChatRequest,
    ChatResult,
    EmbeddingOutput,
    EmbeddingRequest,
    EmbeddingResult,
    InvocationContext,
    InvocationMetadata,
    ModelUsage,
    OcrOutput,
    OcrRequest,
    OcrResult,
    RerankOutput,
    RerankRequest,
    RerankResult,
    VisionOutput,
    VisionRequest,
    VisionResult,
)
from .errors import (
    CapabilityUnavailableError,
    ModelRateLimitError,
    ModelServerError,
    ModelTimeoutError,
    SchemaParseError,
    SemanticValidationError,
)

DEFAULT_FIXTURE = Path(__file__).with_name("fixtures") / "fake_capabilities.json"


class FakeScenario(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    INVALID_JSON = "invalid_json"
    SEMANTIC_INVALID = "semantic_invalid"


class FakeModelGateway:
    """Implement every capability Protocol without importing network clients."""

    def __init__(
        self,
        *,
        fixture_path: str | Path = DEFAULT_FIXTURE,
        scenarios: dict[str, FakeScenario] | None = None,
        unavailable_capabilities: set[str] | None = None,
    ) -> None:
        self._fixture_path = Path(fixture_path)
        self._fixture = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        self._scenarios = scenarios or {}
        self._unavailable = unavailable_capabilities or set()
        self.calls: list[tuple[str, FakeScenario]] = []

    def chat(self, request: ChatRequest) -> ChatResult:
        parsed = self._parse("chat", ChatOutput)
        return ChatResult(metadata=self._metadata("chat", request.context, parsed), parsed=parsed)

    def observe(self, request: VisionRequest) -> VisionResult:
        parsed = self._parse("vision", VisionOutput)
        return VisionResult(
            metadata=self._metadata("vision", request.context, parsed), parsed=parsed
        )

    def transcribe(self, request: AsrRequest) -> AsrResult:
        parsed = self._parse("asr", AsrOutput)
        return AsrResult(metadata=self._metadata("asr", request.context, parsed), parsed=parsed)

    def recognize(self, request: OcrRequest) -> OcrResult:
        parsed = self._parse("ocr", OcrOutput)
        return OcrResult(metadata=self._metadata("ocr", request.context, parsed), parsed=parsed)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        parsed = self._parse("embedding", EmbeddingOutput)
        if len(parsed.vectors) != len(request.texts):
            raise SemanticValidationError("embedding count does not match input count")
        return EmbeddingResult(
            metadata=self._metadata("embedding", request.context, parsed), parsed=parsed
        )

    def rerank(self, request: RerankRequest) -> RerankResult:
        parsed = self._parse("reranker", RerankOutput)
        if len(parsed.items) > request.top_n or any(
            item.original_index >= len(request.documents) for item in parsed.items
        ):
            raise SemanticValidationError("reranker output exceeds the request bounds")
        return RerankResult(
            metadata=self._metadata("reranker", request.context, parsed), parsed=parsed
        )

    def _parse(self, capability: str, output_type):
        scenario = self._scenario(capability)
        self.calls.append((capability, scenario))
        if capability in self._unavailable:
            raise CapabilityUnavailableError(f"{capability} is not configured")
        if scenario is FakeScenario.TIMEOUT:
            raise ModelTimeoutError(f"fake {capability} timeout")
        if scenario is FakeScenario.RATE_LIMIT:
            raise ModelRateLimitError(f"fake {capability} 429")
        if scenario is FakeScenario.SERVER_ERROR:
            raise ModelServerError(f"fake {capability} 503")
        if scenario is FakeScenario.INVALID_JSON:
            try:
                json.loads('{"incomplete":')
            except json.JSONDecodeError as exc:
                raise SchemaParseError(f"fake {capability} returned invalid JSON") from exc
        raw = self._fixture[capability]
        if capability == "vision" and scenario is FakeScenario.SEMANTIC_INVALID:
            raw = self._fixture["semantic_invalid_vision"]
        elif scenario is FakeScenario.SEMANTIC_INVALID:
            raise SemanticValidationError(f"fake {capability} crossed a semantic boundary")
        try:
            return output_type.model_validate(raw)
        except ValidationError as exc:
            raise SemanticValidationError(
                f"fake {capability} returned schema-shaped but invalid values"
            ) from exc

    def _scenario(self, capability: str) -> FakeScenario:
        return self._scenarios.get(capability, FakeScenario.SUCCESS)

    def _metadata(
        self, capability: str, context: InvocationContext, parsed: Any
    ) -> InvocationMetadata:
        characters = len(json.dumps(parsed.model_dump(mode="json"), ensure_ascii=False))
        return InvocationMetadata(
            provider="fake",
            model=f"fake-{capability}",
            model_revision="fixture.v0.1",
            prompt_version=context.prompt_version,
            config_version=context.config_version,
            latency_ms=1.0,
            usage=ModelUsage(
                input_tokens=10,
                output_tokens=20,
                characters=characters,
                audio_seconds=3.0 if capability == "asr" else 0.0,
                cost_usd=0.001,
            ),
            raw_response_ref=(
                f"fixture://model-gateway/{self._fixture_path.name}#{capability}"
            ),
            provider_request_id=f"fake-{capability}-request",
        )
