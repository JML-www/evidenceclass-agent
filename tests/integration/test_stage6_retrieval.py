from pathlib import Path

from evals.retrieval.run_stage6_eval import run


def test_stage6_complete_offline_acceptance(tmp_path: Path):
    report = run(tmp_path / "stage6")

    assert report["acceptance_passed"] is True
    assert report["chunk_audit"]["sample_size"] == 30
    assert report["chunk_audit"]["passed"] is True
    assert report["retrieval"]["dataset_size"] == 40
    assert report["retrieval"]["recall@5"] >= 0.9
    assert report["retrieval"]["mrr"] >= 0.85
    assert report["retrieval"]["ndcg@5"] >= 0.85
    assert report["metadata_filter_before_scoring"] is True
    assert report["publication_gate_unknown_source_rejected"] is True
    assert report["citations"] == {
        "valid_passed": True,
        "forged_rejected": True,
        "deleted_rejected": True,
    }
    assert report["prompt_injection"]["passed"] is True
    assert len(report["prompt_injection"]["trials"]) == 10
