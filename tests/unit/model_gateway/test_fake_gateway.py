from pathlib import Path

import pytest

from packages.model_gateway import (
    AsrModel,
    ChatModel,
    EmbeddingModel,
    FakeModelGateway,
    FakeScenario,
    OcrModel,
    Reranker,
    VisionModel,
)
from packages.model_gateway.contracts import (
    AsrRequest,
    ChatMessage,
    ChatRequest,
    EmbeddingRequest,
    InvocationContext,
    OcrRequest,
    RerankRequest,
    VisionRequest,
)
from packages.model_gateway.errors import (
    CapabilityUnavailableError,
    ModelRateLimitError,
    ModelServerError,
    ModelTimeoutError,
    SchemaParseError,
    SemanticValidationError,
)

ROOT = Path(__file__).resolve().parents[3]


def _context() -> InvocationContext:
    return InvocationContext(
        prompt_version="test-prompt.v1",
        config_version="test-config.v1",
        timeout_seconds=2.0,
        max_output_tokens=128,
    )


def test_fake_implements_all_six_capability_protocols_with_complete_metadata():
    gateway = FakeModelGateway()
    assert isinstance(gateway, ChatModel)
    assert isinstance(gateway, VisionModel)
    assert isinstance(gateway, AsrModel)
    assert isinstance(gateway, OcrModel)
    assert isinstance(gateway, EmbeddingModel)
    assert isinstance(gateway, Reranker)

    results = [
        gateway.chat(
            ChatRequest(
                messages=[ChatMessage(role="user", content="synthetic")],
                response_schema={"type": "object"},
                context=_context(),
            )
        ),
        gateway.observe(
            VisionRequest(
                image_refs=["fixture://image/001"],
                instruction="observe synthetic markers",
                context=_context(),
            )
        ),
        gateway.transcribe(
            AsrRequest(audio_ref="fixture://audio/001", language="zh", context=_context())
        ),
        gateway.recognize(
            OcrRequest(image_refs=["fixture://image/001"], context=_context())
        ),
        gateway.embed(EmbeddingRequest(texts=["a", "b"], context=_context())),
        gateway.rerank(
            RerankRequest(
                query="q",
                documents=["a", "b"],
                top_n=2,
                context=_context(),
            )
        ),
    ]
    for result in results:
        metadata = result.metadata
        assert metadata.provider == "fake"
        assert metadata.model_revision == "fixture.v0.1"
        assert metadata.prompt_version == "test-prompt.v1"
        assert metadata.config_version == "test-config.v1"
        assert metadata.latency_ms >= 0
        assert metadata.usage.total_tokens > 0
        assert metadata.raw_response_ref.startswith("fixture://")
        assert result.parsed is not None


@pytest.mark.parametrize(
    ("scenario", "error_type"),
    [
        (FakeScenario.TIMEOUT, ModelTimeoutError),
        (FakeScenario.RATE_LIMIT, ModelRateLimitError),
        (FakeScenario.SERVER_ERROR, ModelServerError),
        (FakeScenario.INVALID_JSON, SchemaParseError),
        (FakeScenario.SEMANTIC_INVALID, SemanticValidationError),
    ],
)
def test_fake_vision_supports_required_failure_scenarios(scenario, error_type):
    gateway = FakeModelGateway(scenarios={"vision": scenario})
    request = VisionRequest(
        image_refs=["fixture://image/001"],
        instruction="observe synthetic markers",
        context=_context(),
    )
    with pytest.raises(error_type):
        gateway.observe(request)


def test_fake_can_mark_only_one_capability_unavailable():
    gateway = FakeModelGateway(unavailable_capabilities={"asr"})
    with pytest.raises(CapabilityUnavailableError):
        gateway.transcribe(
            AsrRequest(audio_ref="fixture://audio/001", language="zh", context=_context())
        )
    result = gateway.observe(
        VisionRequest(
            image_refs=["fixture://image/001"],
            instruction="observe synthetic markers",
            context=_context(),
        )
    )
    assert result.parsed.observation.visible_student_count == 18


def test_vendor_sdk_is_confined_to_the_model_gateway():
    forbidden = []
    for root in (ROOT / "apps", ROOT / "packages"):
        for path in root.rglob("*.py"):
            if "model_gateway" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            if "import openai" in source or "from openai" in source:
                forbidden.append(path.relative_to(ROOT))
    assert forbidden == []
