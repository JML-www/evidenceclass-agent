"""Small deterministic local embedding and reranker adapters for offline RAG evaluation."""

from __future__ import annotations

import hashlib
import math
import re
import time

from packages.model_gateway.contracts import (
    EmbeddingOutput,
    EmbeddingRequest,
    EmbeddingResult,
    InvocationMetadata,
    ModelUsage,
    RerankedItem,
    RerankOutput,
    RerankRequest,
    RerankResult,
)

from .contracts import EMBEDDING_DIMENSIONS

LEXEME_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*")


def lexical_features(text: str) -> list[str]:
    normalized = text.casefold()
    lexemes = LEXEME_PATTERN.findall(normalized)
    compact = "".join(lexemes)
    bigrams = [compact[index : index + 2] for index in range(max(0, len(compact) - 1))]
    return lexemes + bigrams


class DeterministicHashEmbeddingAdapter:
    """Feature-hashing baseline; useful for tests, not presented as a learned model."""

    dimensions = EMBEDDING_DIMENSIONS

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        started = time.perf_counter()
        vectors = [self._vector(text) for text in request.texts]
        digest = hashlib.sha256("\x1f".join(request.texts).encode("utf-8")).hexdigest()
        return EmbeddingResult(
            metadata=InvocationMetadata(
                provider="deterministic-local",
                model="feature-hashing-384",
                model_revision="hash-embedding.v0.1",
                prompt_version=request.context.prompt_version,
                config_version=request.context.config_version,
                latency_ms=(time.perf_counter() - started) * 1000,
                usage=ModelUsage(characters=sum(len(text) for text in request.texts), cost_usd=0.0),
                raw_response_ref=f"memory://hash-embedding/{digest}",
            ),
            parsed=EmbeddingOutput(vectors=vectors),
        )

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature in lexical_features(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]


class LexicalOverlapReranker:
    """Optional deterministic Top-N reranker for a transparent offline baseline."""

    def rerank(self, request: RerankRequest) -> RerankResult:
        started = time.perf_counter()
        query = set(lexical_features(request.query))
        scores: list[tuple[int, float]] = []
        for index, document in enumerate(request.documents):
            features = set(lexical_features(document))
            denominator = max(1, len(query))
            score = min(1.0, len(query & features) / denominator)
            scores.append((index, score))
        scores.sort(key=lambda item: (-item[1], item[0]))
        selected = scores[: request.top_n]
        digest = hashlib.sha256(request.query.encode("utf-8")).hexdigest()
        return RerankResult(
            metadata=InvocationMetadata(
                provider="deterministic-local",
                model="lexical-overlap",
                model_revision="lexical-reranker.v0.1",
                prompt_version=request.context.prompt_version,
                config_version=request.context.config_version,
                latency_ms=(time.perf_counter() - started) * 1000,
                usage=ModelUsage(
                    characters=len(request.query) + sum(map(len, request.documents)),
                    cost_usd=0.0,
                ),
                raw_response_ref=f"memory://lexical-reranker/{digest}",
            ),
            parsed=RerankOutput(
                items=[RerankedItem(original_index=index, score=score) for index, score in selected]
            ),
        )
