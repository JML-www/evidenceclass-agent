import wave
from dataclasses import dataclass

from packages.model_gateway import FasterWhisperAdapter, RapidOcrAdapter
from packages.model_gateway.contracts import AsrRequest, InvocationContext, OcrRequest
from packages.model_gateway.raw_responses import InMemoryRawResponseSink


def _context() -> InvocationContext:
    return InvocationContext(
        prompt_version="local-media-test.v1",
        config_version="local-media-test.v1",
        timeout_seconds=2.0,
        max_output_tokens=128,
    )


@dataclass
class _WhisperSegment:
    start: float
    end: float
    text: str


@dataclass
class _WhisperInfo:
    language: str


class _WhisperModel:
    def transcribe(self, *args, **kwargs):
        return iter([_WhisperSegment(0.0, 0.8, " 合成转写 ")]), _WhisperInfo("zh")


def test_faster_whisper_adapter_uses_explicit_model_and_raw_reference(tmp_path):
    audio = tmp_path / "audio.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)
    sink = InMemoryRawResponseSink()
    adapter = FasterWhisperAdapter(
        model_name_or_path="injected-tiny",
        raw_response_sink=sink,
        model=_WhisperModel(),
    )

    result = adapter.transcribe(
        AsrRequest(audio_ref=str(audio), language="zh", context=_context())
    )

    assert result.parsed.segments[0].text == "合成转写"
    assert result.metadata.provider == "faster-whisper-local"
    assert result.metadata.model_revision == "configured:injected-tiny"
    assert result.metadata.usage.audio_seconds == 1.0
    assert result.metadata.raw_response_ref in sink.objects


class _RapidEngine:
    def __call__(self, path):
        return (
            [
                [
                    [[10, 20], [110, 20], [110, 60], [10, 60]],
                    "Synthetic OCR",
                    0.92,
                ]
            ],
            [0.01, 0.01, 0.01],
        )


def test_rapidocr_adapter_normalizes_boxes_without_importing_provider_in_tests(tmp_path):
    image = tmp_path / "frame.png"
    image.write_bytes(b"synthetic placeholder; injected engine does not decode it")
    sink = InMemoryRawResponseSink()
    adapter = RapidOcrAdapter(
        raw_response_sink=sink,
        engine=_RapidEngine(),
        image_size_loader=lambda _: (200, 100),
    )

    result = adapter.recognize(
        OcrRequest(image_refs=[image.as_uri()], context=_context())
    )

    item = result.parsed.items[0]
    assert item.text == "Synthetic OCR"
    assert item.box.model_dump() == {"x": 0.05, "y": 0.2, "width": 0.5, "height": 0.4}
    assert result.metadata.raw_response_ref in sink.objects
