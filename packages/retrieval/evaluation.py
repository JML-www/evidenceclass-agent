"""Retrieval-only Recall, reciprocal-rank, and nDCG evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .contracts import RetrievalFilters
from .service import RetrievalService


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    case_id: str
    query: str
    relevant_chunk_ids: frozenset[str]
    filters: RetrievalFilters


def evaluate_retrieval(
    service: RetrievalService,
    cases: list[RetrievalEvaluationCase],
    *,
    recall_k: int = 5,
    ndcg_k: int = 5,
) -> dict[str, object]:
    if not cases:
        raise ValueError("retrieval evaluation requires at least one case")
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    failures: list[dict[str, object]] = []
    for case in cases:
        result = service.retrieve(case.query, case.filters)
        ranked_ids = [context.chunk.chunk_id for context in result.contexts]
        recall = len(set(ranked_ids[:recall_k]) & case.relevant_chunk_ids) / len(
            case.relevant_chunk_ids
        )
        recalls.append(recall)
        relevant_ranks = [
            index
            for index, chunk_id in enumerate(ranked_ids, start=1)
            if chunk_id in case.relevant_chunk_ids
        ]
        reciprocal_rank = 1.0 / min(relevant_ranks) if relevant_ranks else 0.0
        reciprocal_ranks.append(reciprocal_rank)
        dcg = sum(
            1.0 / math.log2(index + 1)
            for index, chunk_id in enumerate(ranked_ids[:ndcg_k], start=1)
            if chunk_id in case.relevant_chunk_ids
        )
        ideal_count = min(len(case.relevant_chunk_ids), ndcg_k)
        ideal_dcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_count + 1))
        ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
        ndcgs.append(ndcg)
        if recall < 1.0:
            failures.append(
                {
                    "case_id": case.case_id,
                    "query": case.query,
                    "expected": sorted(case.relevant_chunk_ids),
                    "retrieved": ranked_ids,
                }
            )
    return {
        "dataset_size": len(cases),
        f"recall@{recall_k}": sum(recalls) / len(recalls),
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks),
        f"ndcg@{ndcg_k}": sum(ndcgs) / len(ndcgs),
        "failed_cases": failures,
    }
