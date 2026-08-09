import json
from types import SimpleNamespace

import httpx
import pytest
from openai import PermissionDeniedError

from packages.model_gateway.contracts import (
    ChatMessage,
    ChatRequest,
    InvocationContext,
    VisionOutput,
    VisionRequest,
)
from packages.model_gateway.errors import ModelPermissionDeniedError
from packages.model_gateway.fake import FakeModelGateway
from packages.model_gateway.openai_compatible import OpenAICompatibleAdapter, TokenPricing
from packages.model_gateway.raw_responses import InMemoryRawResponseSink


class StubCompletions:
    def __init__(self, content):
        self.content = content
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(content=self.content, refusal=None)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
        return SimpleNamespace(
            choices=[choice],
            usage=usage,
            model="compatible-model-revision",
            id="provider-request-1",
            model_dump_json=lambda: json.dumps({"id": "provider-request-1"}),
        )


class ErrorCompletions:
    def create(self, **_kwargs):
        response = httpx.Response(
            403,
            request=httpx.Request("POST", "https://example.invalid/v1/chat/completions"),
        )
        raise PermissionDeniedError("blocked", response=response, body=None)


def _client(content):
    completions = StubCompletions(content)
    return SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    ), completions


def _context():
    return InvocationContext(
        prompt_version="prompt.v1",
        config_version="config.v1",
        timeout_seconds=10.0,
        max_output_tokens=256,
    )


def test_chat_uses_strict_schema_and_returns_accounted_raw_reference():
    client, completions = _client('{"answer":"synthetic"}')
    sink = InMemoryRawResponseSink()
    adapter = OpenAICompatibleAdapter(
        api_key="test-only",
        base_url="https://example.invalid/v1",
        model="explicit-model",
        raw_response_sink=sink,
        pricing=TokenPricing(1.0, 2.0),
        client=client,
    )
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    result = adapter.chat(
        ChatRequest(
            messages=[ChatMessage(role="user", content="synthetic")],
            response_schema=schema,
            context=_context(),
        )
    )
    response_format = completions.kwargs["response_format"]
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == schema
    assert completions.kwargs["max_completion_tokens"] == 256
    assert result.parsed.structured == {"answer": "synthetic"}
    assert result.metadata.usage.cost_usd == 0.0002
    assert result.metadata.raw_response_ref in sink.objects


def test_vision_uses_data_reference_and_validates_semantic_contract():
    vision_json = FakeModelGateway().observe(
        VisionRequest(
            image_refs=["fixture://image/001"],
            instruction="synthetic",
            context=_context(),
        )
    ).parsed.model_dump_json()
    client, completions = _client(vision_json)
    adapter = OpenAICompatibleAdapter(
        api_key="test-only",
        base_url="https://example.invalid/v1",
        model="explicit-model",
        raw_response_sink=InMemoryRawResponseSink(),
        client=client,
    )
    result = adapter.observe(
        VisionRequest(
            image_refs=["data:image/png;base64,AAAA"],
            instruction="observe",
            context=_context(),
        )
    )
    user_content = completions.kwargs["messages"][1]["content"]
    assert user_content[1]["image_url"]["url"].startswith("data:image/png")
    provider_schema = completions.kwargs["response_format"]["json_schema"]["schema"]
    assert set(provider_schema["required"]) == set(provider_schema["properties"])
    assert provider_schema["additionalProperties"] is False
    assert '"minimum"' not in json.dumps(provider_schema)
    assert "$defs" in VisionOutput.model_json_schema()
    assert result.parsed.observation.visible_student_count == 18
    assert result.metadata.usage.cost_usd is None


def test_environment_factory_never_supplies_a_hidden_default_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(ValueError, match="model"):
        OpenAICompatibleAdapter.from_env(raw_response_sink=InMemoryRawResponseSink())


def test_provider_permission_denial_is_stable_and_never_misclassified_as_bad_input():
    client = SimpleNamespace(chat=SimpleNamespace(completions=ErrorCompletions()))
    adapter = OpenAICompatibleAdapter(
        api_key="test-only",
        base_url="https://example.invalid/v1",
        model="explicit-model",
        raw_response_sink=InMemoryRawResponseSink(),
        client=client,
    )
    with pytest.raises(ModelPermissionDeniedError) as error:
        adapter.chat(
            ChatRequest(
                messages=[ChatMessage(role="user", content="synthetic")],
                response_schema={"type": "object"},
                context=_context(),
            )
        )
    assert error.value.error_code == "MODEL_PERMISSION_DENIED"
