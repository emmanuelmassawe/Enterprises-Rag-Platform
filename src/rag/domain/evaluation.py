"""Pure scoring functions for versioned retrieval and answer evaluations."""

from __future__ import annotations

import math
from collections.abc import Sequence


def retrieval_metrics(
    expected_sources: Sequence[str], ranked_sources: Sequence[str], k: int
) -> dict[str, float]:
    """Return recall@k, reciprocal rank, and normalized discounted cumulative gain."""
    if k < 1:
        raise ValueError("k must be positive")
    expected = set(expected_sources)
    ranked = list(ranked_sources[:k])
    if not expected:
        return {"recall_at_k": 1.0, "mrr": 1.0, "ndcg": 1.0}
    recall = len(expected.intersection(ranked)) / len(expected)
    reciprocal_rank = next(
        (1.0 / rank for rank, source in enumerate(ranked, start=1) if source in expected), 0.0
    )
    dcg = sum(
        1.0 / math.log2(rank + 1) for rank, source in enumerate(ranked, 1) if source in expected
    )
    ideal_hits = min(len(expected), len(ranked))
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return {
        "recall_at_k": recall,
        "mrr": reciprocal_rank,
        "ndcg": dcg / ideal_dcg if ideal_dcg else 0.0,
    }


def citation_accuracy(expected_sources: Sequence[str], cited_sources: Sequence[str]) -> float:
    """Measure the share of emitted citations that point to an expected source."""
    if not cited_sources:
        return 1.0 if not expected_sources else 0.0
    expected = set(expected_sources)
    return sum(source in expected for source in cited_sources) / len(cited_sources)


def refusal_accuracy(expected_refusal: bool, actual_refusal: bool) -> float:
    """Return binary refusal correctness for one example."""
    return float(expected_refusal == actual_refusal)


def mean(values: Sequence[float]) -> float:
    """Return the arithmetic mean, rejecting empty input explicitly."""
    if not values:
        raise ValueError("at least one score is required")
    return sum(values) / len(values)
