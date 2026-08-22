"""One real Chat/Vision path behind the provider-neutral gateway contracts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from .contracts import (
    ChatOutput,
    ChatRequest,
    ChatResult,
    InvocationContext,
    InvocationMetadata,
    ModelUsage,
    StructuredVisionOutput,
    StructuredVisionRequest,
    StructuredVisionResult,
    VisionOutput,
    VisionRequest,
    VisionResult,
)
from .errors import (
    DeterministicModelRequestError,
    ModelAuthenticationError,
    ModelContentPolicyError,
    ModelPermissionDeniedError,
    ModelRateLimitError,
    ModelServerError,
    ModelTimeoutError,
    SchemaParseError,
    SemanticValidationError,
)
from .raw_responses import RawResponseSink

_UNSUPPORTED_PROVIDER_SCHEMA_KEYS = {
    "default",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "format",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
    "pattern",
}


def _strict_provider_schema(value: Any) -> Any:
    """Convert validation-rich Pydantic JSON Schema to the provider's strict subset."""

    if isinstance(value, list):
        return [_strict_provider_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized = {
        key: _strict_provider_schema(item)
        for key, item in value.items()
        if key not in _UNSUPPORTED_PROVIDER_SCHEMA_KEYS
    }
    properties = normalized.get("properties")
    if isinstance(properties, dict):
        normalized["required"] = list(properties)
        normalized["additionalProperties"] = False
    return normalized


@dataclass(frozen=True)
class TokenPricing:
    input_per_million_usd: float
    output_per_million_usd: float

    def __post_init__(self) -> None:
        if self.input_per_million_usd < 0 or self.output_per_million_usd < 0:
            raise ValueError("token pricing cannot be negative")

    def calculate(self, input_tokens: int, output_tokens: int) -> float:
        return round(
            input_tokens * self.input_per_million_usd / 1_000_000
            + output_tokens * self.output_per_million_usd / 1_000_000,
            10,
        )


class OpenAICompatibleAdapter:
    """Use Chat Completions while containing the concrete SDK in this module."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        raw_response_sink: RawResponseSink,
        provider: str = "openai-compatible",
        pricing: TokenPricing | None = None,
        client: OpenAI | None = None,
    ) -> None:
        if not api_key or not base_url or not model:
            raise ValueError("api_key, base_url, and model are required")
        self._model = model
        self._provider = provider
        self._pricing = pricing
        self._raw_sink = raw_response_sink
        self._client = client or OpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=0,
        )

    @classmethod
    def from_env(
        cls,
        *,
        raw_response_sink: RawResponseSink,
        model: str | None = None,
    ) -> OpenAICompatibleAdapter:
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "")
        selected_model = model or os.getenv("OPENAI_MODEL", "")
        input_rate = os.getenv("OPENAI_INPUT_COST_PER_MILLION", "")
        output_rate = os.getenv("OPENAI_OUTPUT_COST_PER_MILLION", "")
        if bool(input_rate) != bool(output_rate):
            raise ValueError("both OpenAI token pricing rates must be configured together")
        pricing = TokenPricing(float(input_rate), float(output_rate)) if input_rate else None
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=selected_model,
            raw_response_sink=raw_response_sink,
            pricing=pricing,
        )

    def chat(self, request: ChatRequest) -> ChatResult:
        messages = [message.model_dump() for message in request.messages]
        raw, metadata = self._complete(
            messages=messages,
            schema=request.response_schema,
            schema_name=request.schema_name,
            context=request.context,
        )
        parsed = ChatOutput(
            text=json.dumps(raw, ensure_ascii=False, sort_keys=True),
            structured=raw,
        )
        return ChatResult(metadata=metadata, parsed=parsed)

    def observe(self, request: VisionRequest) -> VisionResult:
        content: list[dict[str, Any]] = [{"type": "text", "text": request.instruction}]
        content.extend(
            {
                "type": "image_url",
                "image_url": {"url": image_ref, "detail": "low"},
            }
            for image_ref in request.image_refs
        )
        raw, metadata = self._complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return only observable facts. Do not infer identity, emotion, "
                        "ability, diagnosis, or disciplinary conclusions."
                    ),
                },
                {"role": "user", "content": content},
            ],
            schema=VisionOutput.model_json_schema(),
            schema_name="classroom_visual_observation",
            context=request.context,
        )
        try:
            parsed = VisionOutput.model_validate(raw)
        except ValidationError as exc:
            raise SemanticValidationError(
                "vision output crossed a semantic boundary",
                raw_response_ref=metadata.raw_response_ref,
            ) from exc
        return VisionResult(metadata=metadata, parsed=parsed)

    def observe_structured(self, request: StructuredVisionRequest) -> StructuredVisionResult:
        content: list[dict[str, Any]] = [{"type": "text", "text": request.instruction}]
        content.extend(
            {
                "type": "image_url",
                "image_url": {"url": image_ref, "detail": "low"},
            }
            for image_ref in request.image_refs
        )
        raw, metadata = self._complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Report only directly observable labels requested by the Schema. "
                        "Do not infer identity, emotion, attention, ability, diagnosis, "
                        "discipline, or whole-lesson quality."
                    ),
                },
                {"role": "user", "content": content},
            ],
            schema=request.response_schema,
            schema_name=request.schema_name,
            context=request.context,
        )
        return StructuredVisionResult(
            metadata=metadata,
            parsed=StructuredVisionOutput(structured=raw),
        )

    def _complete(
        self,
        *,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        schema_name: str,
        context: InvocationContext,
    ) -> tuple[dict[str, Any], InvocationMetadata]:
        started = perf_counter()
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_completion_tokens=context.max_output_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": _strict_provider_schema(schema),
                    },
                },
                timeout=context.timeout_seconds,
            )
        except APITimeoutError as exc:
            raise ModelTimeoutError("provider request timed out") from exc
        except RateLimitError as exc:
            raise ModelRateLimitError("provider returned 429") from exc
        except AuthenticationError as exc:
            raise ModelAuthenticationError("provider authentication failed") from exc
        except PermissionDeniedError as exc:
            raise ModelPermissionDeniedError("provider denied model execution") from exc
        except BadRequestError as exc:
            if getattr(exc, "code", None) in {"content_filter", "safety_violation"}:
                raise ModelContentPolicyError("provider blocked the request") from exc
            raise DeterministicModelRequestError("provider rejected the request") from exc
        except APIConnectionError as exc:
            raise ModelServerError("provider connection failed") from exc
        except APIStatusError as exc:
            if exc.status_code >= 500:
                raise ModelServerError(f"provider returned {exc.status_code}") from exc
            raise DeterministicModelRequestError(
                f"provider returned non-retryable status {exc.status_code}"
            ) from exc

        message = completion.choices[0].message
        if getattr(message, "refusal", None):
            raise ModelContentPolicyError("provider refused the request")
        if completion.choices[0].finish_reason == "content_filter":
            raise ModelContentPolicyError("provider content filter stopped the response")
        content = message.content
        if not isinstance(content, str):
            raise SchemaParseError("provider response did not contain text JSON")

        raw_response_ref = self._raw_sink.put(completion.model_dump_json().encode("utf-8"))
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SchemaParseError(
                "provider response was not valid JSON",
                raw_response_ref=raw_response_ref,
            ) from exc
        if not isinstance(parsed, dict):
            raise SchemaParseError(
                "provider response JSON root must be an object",
                raw_response_ref=raw_response_ref,
            )

        usage = completion.usage
        input_tokens = int(usage.prompt_tokens) if usage is not None else 0
        output_tokens = int(usage.completion_tokens) if usage is not None else 0
        cost = (
            self._pricing.calculate(input_tokens, output_tokens)
            if self._pricing is not None
            else None
        )
        characters = len(content) + sum(
            len(json.dumps(item, ensure_ascii=False)) for item in messages
        )
        metadata = InvocationMetadata(
            provider=self._provider,
            model=self._model,
            model_revision=completion.model,
            prompt_version=context.prompt_version,
            config_version=context.config_version,
            latency_ms=round((perf_counter() - started) * 1000, 3),
            usage=ModelUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                characters=characters,
                audio_seconds=0.0,
                cost_usd=cost,
            ),
            raw_response_ref=raw_response_ref,
            provider_request_id=completion.id,
        )
        return parsed, metadata
