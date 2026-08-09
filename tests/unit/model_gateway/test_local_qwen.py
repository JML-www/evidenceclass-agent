from contextlib import nullcontext

from packages.model_gateway.contracts import InvocationContext, VisionRequest
from packages.model_gateway.fake import FakeModelGateway
from packages.model_gateway.local_qwen import LocalQwen35Adapter
from packages.model_gateway.raw_responses import InMemoryRawResponseSink


class FakeTensor:
    def __init__(self, length):
        self.shape = (1, length)

    def __getitem__(self, key):
        _rows, columns = key
        start = columns.start or 0
        return FakeTensor(max(0, self.shape[-1] - start))


class FakeBatch(dict):
    def to(self, _device):
        return self


class StubProcessor:
    def __init__(self, output):
        self.output = output
        self.messages = None

    def apply_chat_template(self, messages, **_kwargs):
        self.messages = messages
        return FakeBatch(input_ids=FakeTensor(4))

    def batch_decode(self, _tokens, **_kwargs):
        return [self.output]


class StubModel:
    device = "cpu"

    def generate(self, **_kwargs):
        return FakeTensor(7)


class StubTorch:
    @staticmethod
    def inference_mode():
        return nullcontext()


def test_local_qwen_is_optional_temporary_adapter_with_same_vision_contract(tmp_path):
    model_path = tmp_path / "Qwen3.5-0.8B"
    model_path.mkdir()
    (model_path / "config.json").write_text('{"model_type":"qwen3_5"}', encoding="utf-8")
    expected = FakeModelGateway().observe(
        VisionRequest(
            image_refs=["fixture://image"],
            instruction="synthetic",
            context=InvocationContext(
                prompt_version="p.v1",
                config_version="c.v1",
                timeout_seconds=2.0,
                max_output_tokens=64,
            ),
        )
    ).parsed
    processor = StubProcessor(expected.model_dump_json())
    sink = InMemoryRawResponseSink()
    adapter = LocalQwen35Adapter(
        model_path=model_path,
        raw_response_sink=sink,
        model=StubModel(),
        processor=processor,
        torch_module=StubTorch(),
    )
    result = adapter.observe(
        VisionRequest(
            image_refs=["data:image/png;base64,AAAA"],
            instruction="observe only synthetic markers",
            context=InvocationContext(
                prompt_version="local-qwen-temporary.v1",
                config_version="local-qwen-test.v1",
                timeout_seconds=2.0,
                max_output_tokens=64,
            ),
        )
    )
    assert result.metadata.provider == "local-qwen-temporary"
    assert result.metadata.model == "Qwen3.5-0.8B"
    assert result.metadata.usage.input_tokens == 4
    assert result.metadata.usage.output_tokens == 3
    assert result.metadata.usage.cost_usd == 0.0
    assert result.parsed.observation.visible_student_count == 18
    assert processor.messages[0]["content"][0]["type"] == "image"
    assert result.metadata.raw_response_ref in sink.objects
