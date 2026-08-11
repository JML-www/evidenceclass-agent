"""Provider-neutral model capabilities, Fake adapters, and reliability policies."""

from .contracts import (
    AsrRequest,
    AsrResult,
    ChatRequest,
    ChatResult,
    EmbeddingRequest,
    EmbeddingResult,
    OcrRequest,
    OcrResult,
    RerankRequest,
    RerankResult,
    StructuredVisionRequest,
    StructuredVisionResult,
    VisionRequest,
    VisionResult,
)
from .fake import FakeModelGateway, FakeScenario
from .faster_whisper import FasterWhisperAdapter
from .interfaces import (
    AsrModel,
    ChatModel,
    EmbeddingModel,
    OcrModel,
    Reranker,
    StructuredVisionModel,
    VisionModel,
)
from .local_qwen import LocalQwen35Adapter
from .rapidocr import RapidOcrAdapter

__all__ = [
    "AsrModel",
    "AsrRequest",
    "AsrResult",
    "ChatModel",
    "ChatRequest",
    "ChatResult",
    "EmbeddingModel",
    "EmbeddingRequest",
    "EmbeddingResult",
    "FakeModelGateway",
    "FakeScenario",
    "FasterWhisperAdapter",
    "LocalQwen35Adapter",
    "OcrModel",
    "OcrRequest",
    "OcrResult",
    "RerankRequest",
    "RerankResult",
    "Reranker",
    "RapidOcrAdapter",
    "StructuredVisionModel",
    "StructuredVisionRequest",
    "StructuredVisionResult",
    "VisionModel",
    "VisionRequest",
    "VisionResult",
]
