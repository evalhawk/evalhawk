import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from evalhawk.stats.retrieval import (
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    retrieval_summary,
)

RETRIEVED = ["d3", "d1", "d7", "d2", "d9"]
RELEVANT = ["d1", "d2"]


def test_hand_computed_values() -> None:
    assert hit_at_k(RETRIEVED, RELEVANT, 1) == 0.0
    assert hit_at_k(RETRIEVED, RELEVANT, 2) == 1.0
    assert recall_at_k(RETRIEVED, RELEVANT, 3) == 0.5  # d1 found, d2 at rank 4
    assert recall_at_k(RETRIEVED, RELEVANT, 5) == 1.0
    assert precision_at_k(RETRIEVED, RELEVANT, 5) == pytest.approx(2 / 5)
    assert precision_at_k(["d1"], RELEVANT, 3) == pytest.approx(1 / 3)  # empty slots miss
    assert reciprocal_rank(RETRIEVED, RELEVANT) == 0.5  # first relevant at rank 2
    assert reciprocal_rank(["x", "y"], RELEVANT) == 0.0
    # nDCG@5: DCG = 1/log2(3) + 1/log2(5); IDCG = 1/log2(2) + 1/log2(3)
    expected = (1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3))
    assert ndcg_at_k(RETRIEVED, RELEVANT, 5) == pytest.approx(expected)
    assert ndcg_at_k(["d1", "d2"], RELEVANT, 5) == pytest.approx(1.0)  # perfect ranking


@given(
    retrieved=st.lists(st.sampled_from([f"d{i}" for i in range(8)]), unique=True, max_size=8),
    relevant=st.lists(st.sampled_from([f"d{i}" for i in range(8)]), unique=True, min_size=1),
    k=st.integers(1, 8),
)
def test_metrics_are_fractions_and_recall_grows_with_k(
    retrieved: list[str], relevant: list[str], k: int
) -> None:
    for metric in (hit_at_k, recall_at_k, precision_at_k, ndcg_at_k):
        assert 0.0 <= metric(retrieved, relevant, k) <= 1.0 + 1e-12
    assert recall_at_k(retrieved, relevant, k) <= recall_at_k(retrieved, relevant, k + 1)
    assert 0.0 <= reciprocal_rank(retrieved, relevant) <= 1.0


def test_summary_has_intervals_and_clusters_widen_them() -> None:
    rng = np.random.default_rng(0)
    queries = [(["a", "b"], ["a"]) if i % 3 else (["x", "a"], ["a"]) for i in range(60)]
    summary = retrieval_summary(queries, k=1, rng=rng)
    assert summary.hit.point == pytest.approx(40 / 60)
    assert summary.hit.low < summary.hit.point < summary.hit.high
    assert summary.mrr.point == pytest.approx((40 * 1 + 20 * 0.5) / 60)
    clustered = retrieval_summary(
        queries, k=1, rng=np.random.default_rng(0), clusters=[str(i // 6) for i in range(60)]
    )
    assert clustered.hit.point == pytest.approx(summary.hit.point)


def test_bad_inputs() -> None:
    with pytest.raises(ValueError, match="k must be"):
        hit_at_k(["a"], ["a"], 0)
    with pytest.raises(ValueError, match="at least one document"):
        recall_at_k(["a"], [], 1)
    with pytest.raises(ValueError, match="at least one query"):
        retrieval_summary([], k=3, rng=np.random.default_rng(0))
