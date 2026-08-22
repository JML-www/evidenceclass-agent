"""Structured query rewrite, Top-20 recall, optional Top-5 rerank, and context budget."""

from __future__ import annotations

import re

from packages.model_gateway.contracts import (
    EmbeddingRequest,
    InvocationContext,
    RerankRequest,
)
from packages.model_gateway.interfaces import EmbeddingModel, Reranker

from .contracts import (
    RetrievalFilters,
    RetrievalResult,
    RetrievedContext,
    ScoredChunk,
    StructuredQuery,
)
from .parsing import TOKEN_PATTERN, count_tokens
from .stores import VectorStore

QUERY_SPACE_PATTERN = re.compile(r"\s+")
QUERY_REWRITE_VERSION = "classroom-query-rewrite.v0.1"
DOMAIN_QUERY_EXPANSIONS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("授权", "许可证"), ("authorization", "license", "publication gate")),
    (("租户", "候选"), ("workspace boundary", "metadata filter", "candidate set")),
    (("抽样", "整堂课"), ("sampled occurrence", "whole lesson duration")),
    (("说话人分离", "师生发言"), ("diarization", "speaker role", "speech ratios")),
    (("损坏容器", "坏帧"), ("probe before model", "ffprobe", "full decode validation")),
    (("重试", "重复相加"), ("segment idempotency", "retry", "duplicate")),
    (("忽略系统规则", "工具权限"), ("tool authorization", "code-owned whitelist")),
    (("删除", "知识块"), ("citation existence", "deleted chunk")),
    (("mrr", "ndcg"), ("retrieval metrics", "reciprocal rank", "discounted gain")),
    (("system prompt",), ("prompt leakage gate", "protected prompt material")),
)


class QueryRewriter:
    """Deterministic structural rewrite; metadata filters remain caller-owned code."""

    def rewrite(self, query: str, filters: RetrievalFilters) -> StructuredQuery:
        base_normalized = QUERY_SPACE_PATTERN.sub(" ", query.strip().casefold())
        if not base_normalized:
            raise ValueError("retrieval query cannot be blank")
        expansions = [
            expansion
            for triggers, values in DOMAIN_QUERY_EXPANSIONS
            if all(trigger in base_normalized for trigger in triggers)
            for expansion in values
        ]
        normalized = " ".join((base_normalized, *expansions))
        terms = list(dict.fromkeys(match.group(0) for match in TOKEN_PATTERN.finditer(normalized)))
        if not terms:
            raise ValueError("retrieval query has no searchable terms")
        return StructuredQuery(
            rewrite_version=QUERY_REWRITE_VERSION,
            original=query,
            normalized=normalized,
            terms=terms,
            filters=filters,
        )


class RetrievalService:
    def __init__(
        self,
        store: VectorStore,
        embedding_model: EmbeddingModel,
        *,
        reranker: Reranker | None = None,
        recall_k: int = 20,
        context_k: int = 5,
        context_token_budget: int = 900,
    ) -> None:
        if recall_k < context_k:
            raise ValueError("recall_k cannot be smaller than context_k")
        self._store = store
        self._embedding_model = embedding_model
        self._reranker = reranker
        self._recall_k = recall_k
        self._context_k = context_k
        self._context_token_budget = context_token_budget
        self._rewriter = QueryRewriter()

    def retrieve(self, query: str, filters: RetrievalFilters) -> RetrievalResult:
        structured = self._rewriter.rewrite(query, filters)
        embedding = self._embedding_model.embed(
            EmbeddingRequest(
                texts=[structured.normalized],
                context=InvocationContext(
                    prompt_version="retrieval-query.v0.1",
                    config_version="hash-embedding-384.v0.1",
                    timeout_seconds=10.0,
                    max_output_tokens=1,
                ),
            )
        ).parsed.vectors[0]
        candidates = self._store.search(embedding, filters, top_k=self._recall_k)
        ranked = self._rerank(structured.normalized, candidates)
        contexts, duplicates_dropped, budget_dropped = self._budget(ranked)
        return RetrievalResult(
            query=structured,
            candidate_chunk_ids=[item.chunk.chunk_id for item in candidates],
            contexts=contexts,
            context_tokens=sum(item.included_tokens for item in contexts),
            duplicates_dropped=duplicates_dropped,
            budget_dropped=budget_dropped,
        )

    def _rerank(self, query: str, candidates: list[ScoredChunk]) -> list[ScoredChunk]:
        if not candidates:
            return []
        if self._reranker is None:
            return candidates[: self._context_k]
        result = self._reranker.rerank(
            RerankRequest(
                query=query,
                documents=[item.chunk.content for item in candidates],
                top_n=min(self._context_k, len(candidates)),
                context=InvocationContext(
                    prompt_version="retrieval-rerank.v0.1",
                    config_version="lexical-reranker.v0.1",
                    timeout_seconds=10.0,
                    max_output_tokens=1,
                ),
            )
        )
        ranked: list[ScoredChunk] = []
        for item in result.parsed.items:
            candidate = candidates[item.original_index]
            ranked.append(candidate.model_copy(update={"rerank_score": item.score}))
        return ranked

    def _budget(self, ranked: list[ScoredChunk]) -> tuple[list[RetrievedContext], int, int]:
        remaining = self._context_token_budget
        contexts: list[RetrievedContext] = []
        seen_hashes: set[str] = set()
        duplicates_dropped = 0
        budget_dropped = 0
        for item in ranked:
            chunk = item.chunk
            if chunk.content_sha256 in seen_hashes:
                duplicates_dropped += 1
                continue
            seen_hashes.add(chunk.content_sha256)
            if remaining <= 0:
                budget_dropped += 1
                continue
            if chunk.token_count <= remaining:
                content = chunk.content
                included_tokens = chunk.token_count
                truncated = False
            else:
                content = self._truncate(chunk.content, remaining)
                included_tokens = max(1, count_tokens(content))
                truncated = True
                budget_dropped += 1
            contexts.append(
                RetrievedContext(
                    chunk=chunk,
                    score=item.effective_score,
                    presented_content=content,
                    included_tokens=included_tokens,
                    truncated=truncated,
                )
            )
            remaining -= included_tokens
        return contexts, duplicates_dropped, budget_dropped

    @staticmethod
    def _truncate(text: str, token_budget: int) -> str:
        matches = list(TOKEN_PATTERN.finditer(text))
        if not matches or token_budget <= 0:
            return "[context omitted]"
        end = matches[min(token_budget, len(matches)) - 1].end()
        return text[:end].strip()
