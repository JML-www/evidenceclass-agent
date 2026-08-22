"""Optional local Qwen3.5 adapter used only for temporary phase-4 functional proof."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any

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
from .errors import SchemaParseError, SemanticValidationError
from .raw_responses import RawResponseSink


class LocalQwen35Adapter:
    """Load a local multimodal checkpoint without making it a core dependency."""

    provider = "local-qwen-temporary"

    def __init__(
        self,
        *,
        model_path: str | Path,
        raw_response_sink: RawResponseSink,
        model: Any | None = None,
        processor: Any | None = None,
        torch_module: Any | None = None,
    ) -> None:
        self._model_path = Path(model_path).resolve()
        if not (self._model_path / "config.json").is_file():
            raise ValueError("local Qwen model_path must contain config.json")
        self._raw_sink = raw_response_sink
        if model is None or processor is None or torch_module is None:
            try:
                import torch
                from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration
            except ImportError as exc:
                raise RuntimeError(
                    "install the local-qwen optional runtime before loading Qwen3.5"
                ) from exc
            torch_module = torch
            processor = AutoProcessor.from_pretrained(
                self._model_path,
                local_files_only=True,
            )
            model = Qwen3_5ForConditionalGeneration.from_pretrained(
                self._model_path,
                dtype="auto",
                device_map="auto",
                local_files_only=True,
            )
            model.eval()
        self._model = model
        self._processor = processor
        self._torch = torch_module
        self._revision = self._config_revision()

    def chat(self, request: ChatRequest) -> ChatResult:
        schema = json.dumps(request.response_schema, ensure_ascii=False, sort_keys=True)
        messages = [message.model_dump() for message in request.messages]
        messages.append(
            {
                "role": "user",
                "content": (
                    "Return only one JSON object with no Markdown fence. It must satisfy: " + schema
                ),
            }
        )
        raw, metadata = self._generate(messages, request.context)
        parsed = ChatOutput(
            text=json.dumps(raw, ensure_ascii=False, sort_keys=True),
            structured=raw,
        )
        return ChatResult(metadata=metadata, parsed=parsed)

    def observe(self, request: VisionRequest) -> VisionResult:
        content: list[dict[str, Any]] = [
            {"type": "image", "url": image_ref} for image_ref in request.image_refs
        ]
        content.append(
            {
                "type": "text",
                "text": (
                    request.instruction
                    + (
                        "\nReturn exactly one compact JSON object with no Markdown or extra "
                        "properties. "
                    )
                    + (
                        "Do not infer identity, emotion, ability, diagnosis, discipline, or "
                        "whole-lesson "
                    )
                    + "quality. Omit the optional regions property entirely. Use this exact shape: "
                    + _VISION_OUTPUT_TEMPLATE
                    + (
                        " Evidence and limitations must each contain one or two short strings. "
                        "Every student "
                    )
                    + "behavior count must be no greater than visible_student_count."
                ),
            }
        )
        compact_context = request.context.model_copy(
            update={"max_output_tokens": min(request.context.max_output_tokens, 320)}
        )
        raw, metadata = self._generate([{"role": "user", "content": content}], compact_context)
        try:
            parsed = VisionOutput.model_validate(raw)
        except ValidationError as exc:
            raise SemanticValidationError(
                "local Qwen output crossed a semantic boundary",
                raw_response_ref=metadata.raw_response_ref,
            ) from exc
        return VisionResult(metadata=metadata, parsed=parsed)

    def observe_structured(self, request: StructuredVisionRequest) -> StructuredVisionResult:
        schema = json.dumps(request.response_schema, ensure_ascii=False, sort_keys=True)
        content: list[dict[str, Any]] = [
            {"type": "image", "url": image_ref} for image_ref in request.image_refs
        ]
        content.append(
            {
                "type": "text",
                "text": (
                    request.instruction
                    + " Return one JSON object only. Do not infer identity, emotion, attention, "
                    + "ability, diagnosis, discipline, or whole-lesson quality. Schema: "
                    + schema
                ),
            }
        )
        raw, metadata = self._generate([{"role": "user", "content": content}], request.context)
        return StructuredVisionResult(
            metadata=metadata,
            parsed=StructuredVisionOutput(structured=raw),
        )

    def _generate(
        self, messages: list[dict[str, Any]], context: InvocationContext
    ) -> tuple[dict[str, Any], InvocationMetadata]:
        started = perf_counter()
        inputs = self._processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self._model.device)
        input_tokens = int(inputs["input_ids"].shape[-1])
        with self._torch.inference_mode():
            generated = self._model.generate(
                **inputs,
                max_new_tokens=context.max_output_tokens,
                do_sample=False,
                use_cache=True,
            )
        trimmed = generated[:, input_tokens:]
        output_tokens = int(trimmed.shape[-1])
        text = self._processor.batch_decode(
            trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()
        raw_response_ref = self._raw_sink.put(
            json.dumps({"generated_text": text}, ensure_ascii=False).encode("utf-8")
        )
        try:
            parsed = json.loads(_normalize_json_text(text))
        except json.JSONDecodeError as exc:
            raise SchemaParseError(
                "local Qwen response was not valid JSON",
                raw_response_ref=raw_response_ref,
            ) from exc
        if not isinstance(parsed, dict):
            raise SchemaParseError(
                "local Qwen JSON root must be an object",
                raw_response_ref=raw_response_ref,
            )
        metadata = InvocationMetadata(
            provider=self.provider,
            model=self._model_path.name,
            model_revision=self._revision,
            prompt_version=context.prompt_version,
            config_version=context.config_version,
            latency_ms=round((perf_counter() - started) * 1000, 3),
            usage=ModelUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                characters=len(text),
                audio_seconds=0.0,
                cost_usd=0.0,
            ),
            raw_response_ref=raw_response_ref,
            provider_request_id=None,
        )
        return parsed, metadata

    def _config_revision(self) -> str:
        digest = hashlib.sha256((self._model_path / "config.json").read_bytes()).hexdigest()
        return f"local-config-sha256:{digest[:16]}"


def _normalize_json_text(text: str) -> str:
    """Accept the common Markdown fence emitted despite a JSON-only prompt."""

    normalized = text.strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        lines = normalized.splitlines()
        normalized = "\n".join(lines[1:-1]).strip()
    if normalized.lower().startswith("json\n"):
        normalized = normalized[5:].lstrip()
    return normalized


_VISION_OUTPUT_TEMPLATE = json.dumps(
    {
        "observation": {
            "frame_id": "frame-1",
            "visible_student_count": 0,
            "focused": 0,
            "head_down_reading_or_writing": 0,
            "hand_raised": 0,
            "discussion": 0,
            "distracted": 0,
            "teacher": {
                "teaching": False,
                "blackboard_writing": False,
                "patrolling": False,
                "questioning": False,
                "organizing_discussion": False,
                "guiding_students": False,
                "using_slides": False,
            },
            "evidence": ["visible fact"],
            "limitations": ["visible-frame limitation"],
            "confidence": 0.0,
        }
    },
    ensure_ascii=False,
    separators=(",", ":"),
)
