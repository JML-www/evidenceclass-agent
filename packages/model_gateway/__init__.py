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
    VisionRequest,
    VisionResult,
)
from .fake import FakeModelGateway, FakeScenario
from .interfaces import AsrModel, ChatModel, EmbeddingModel, OcrModel, Reranker, VisionModel
from .local_qwen import LocalQwen35Adapter

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
    "LocalQwen35Adapter",
    "OcrModel",
    "OcrRequest",
    "OcrResult",
    "RerankRequest",
    "RerankResult",
    "Reranker",
    "VisionModel",
    "VisionRequest",
    "VisionResult",
]
