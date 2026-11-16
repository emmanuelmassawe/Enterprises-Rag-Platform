"""Deterministic tests for evaluation metrics; no external calls or model usage."""

import json
from pathlib import Path

from rag.domain.evaluation import citation_accuracy, refusal_accuracy, retrieval_metrics


def test_req_evl_001_retrieval_metrics_rank_relevant_sources() -> None:
    scores = retrieval_metrics(["a", "b"], ["x", "b", "a"], k=3)

    assert scores["recall_at_k"] == 1.0
    assert scores["mrr"] == 0.5
    assert scores["ndcg"] < 1.0


def test_req_fr_evl_001_golden_eval_dataset_is_versioned_and_synthetic() -> None:
    dataset_path = Path(__file__).parents[1] / "eval" / "golden_dataset.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    assert dataset["dataset_version"] == "synthetic-rag-v1"
    assert len(dataset["examples"]) >= 3
    assert all(
        example["question"] and example["reference_answer"] for example in dataset["examples"]
    )


def test_req_evl_001_empty_relevant_set_has_defined_scores() -> None:
    assert retrieval_metrics([], ["a"], k=5) == {
        "recall_at_k": 1.0,
        "mrr": 1.0,
        "ndcg": 1.0,
    }


def test_req_evl_001_citation_accuracy_and_refusal_accuracy() -> None:
    assert citation_accuracy(["source-a"], ["source-a", "source-b"]) == 0.5
    assert refusal_accuracy(True, True) == 1.0
    assert refusal_accuracy(True, False) == 0.0
