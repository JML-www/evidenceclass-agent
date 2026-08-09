"""Provider-neutral capability Protocols used by business and Agent code."""

from typing import Protocol, runtime_checkable

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


@runtime_checkable
class ChatModel(Protocol):
    def chat(self, request: ChatRequest) -> ChatResult: ...


@runtime_checkable
class VisionModel(Protocol):
    def observe(self, request: VisionRequest) -> VisionResult: ...


@runtime_checkable
class AsrModel(Protocol):
    def transcribe(self, request: AsrRequest) -> AsrResult: ...


@runtime_checkable
class OcrModel(Protocol):
    def recognize(self, request: OcrRequest) -> OcrResult: ...


@runtime_checkable
class EmbeddingModel(Protocol):
    def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...


@runtime_checkable
class Reranker(Protocol):
    def rerank(self, request: RerankRequest) -> RerankResult: ...
