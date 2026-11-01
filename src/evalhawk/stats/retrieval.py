"""Retrieval metrics for RAG: did the search step find the right documents?

Per query, with ``retrieved`` (ranked IDs) and ``relevant`` (the correct IDs), binary
relevance and ``rel(i) = 1`` when the i-th retrieved document is relevant:

* **hit@k** = 1 if any relevant document is in the top k
* **recall@k** = relevant documents in the top k / all relevant documents
* **precision@k** = relevant documents in the top k / k
* **reciprocal rank** = 1 / rank of the first relevant document (0 if none); its mean is MRR
* **nDCG@k** = DCG@k / IDCG@k with ``DCG@k = sum_{i<=k} rel(i) / log2(i + 1)``
  (Järvelin & Kekäläinen, 2002)

Each mean gets a 95% interval from a bootstrap over queries (whole clusters when given),
so retrieval results carry honest error bars like every other EvalHawk number.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from evalhawk.core.results import Estimate
from evalhawk.stats._checks import check_n_boot
from evalhawk.stats.clustered import cluster_bootstrap_means


def _check(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> set[str]:
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
    if not relevant:
        raise ValueError("relevant must contain at least one document ID")
    return set(relevant)


def hit_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    """1.0 if any relevant document is in the top ``k``, else 0.0."""
    wanted = _check(retrieved, relevant, k)
    return float(any(doc in wanted for doc in retrieved[:k]))


def recall_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    """Share of the relevant documents found in the top ``k``."""
    wanted = _check(retrieved, relevant, k)
    return len(wanted.intersection(retrieved[:k])) / len(wanted)


def precision_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    """Share of the top ``k`` slots holding a relevant document (empty slots count as misses)."""
    wanted = _check(retrieved, relevant, k)
    return sum(doc in wanted for doc in retrieved[:k]) / k


def reciprocal_rank(retrieved: Sequence[str], relevant: Sequence[str]) -> float:
    """1 / rank of the first relevant document, or 0.0 if none was retrieved."""
    wanted = _check(retrieved, relevant, 1)
    for rank, doc in enumerate(retrieved, 1):
        if doc in wanted:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    """Normalised discounted cumulative gain with binary relevance."""
    wanted = _check(retrieved, relevant, k)
    dcg = sum(1.0 / math.log2(i + 1) for i, doc in enumerate(retrieved[:k], 1) if doc in wanted)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(k, len(wanted)) + 1))
    return dcg / ideal


@dataclass(frozen=True, slots=True)
class RetrievalSummary:
    """Mean retrieval metrics over queries, each with a bootstrap interval."""

    k: int
    hit: Estimate
    recall: Estimate
    precision: Estimate
    mrr: Estimate
    ndcg: Estimate


def _mean(
    name: str,
    values: npt.NDArray[np.float64],
    clusters: npt.NDArray[np.int64],
    *,
    rng: np.random.Generator,
    n_boot: int,
    confidence: float,
) -> Estimate:
    point = float(values.mean())
    if np.unique(clusters).size < 2:
        return Estimate(point=point, low=point, high=point, n=int(values.size), method=name)
    means = cluster_bootstrap_means(values, clusters, rng=rng, n_boot=n_boot)
    low, high = np.quantile(means, [(1 - confidence) / 2, (1 + confidence) / 2])
    return Estimate(
        point=point,
        low=min(float(low), point),
        high=max(float(high), point),
        n=int(values.size),
        method=f"{name}+bootstrap",
        confidence=confidence,
    )


def retrieval_summary(
    queries: Sequence[tuple[Sequence[str], Sequence[str]]],
    *,
    k: int,
    rng: np.random.Generator,
    clusters: Sequence[str] | None = None,
    n_boot: int = 2000,
    confidence: float = 0.95,
) -> RetrievalSummary:
    """All five metrics over ``(retrieved, relevant)`` pairs, with intervals."""
    if not queries:
        raise ValueError("need at least one query")
    check_n_boot(n_boot)
    columns = np.array(
        [
            [
                hit_at_k(r, rel, k),
                recall_at_k(r, rel, k),
                precision_at_k(r, rel, k),
                reciprocal_rank(r, rel),
                ndcg_at_k(r, rel, k),
            ]
            for r, rel in queries
        ],
        dtype=np.float64,
    )
    if clusters is None:
        codes = np.arange(len(queries), dtype=np.int64)
    else:
        if len(clusters) != len(queries):
            raise ValueError("clusters must have one label per query")
        codes = np.unique(np.asarray(clusters), return_inverse=True)[1].astype(np.int64)
    names = ("hit", "recall", "precision", "mrr", "ndcg")
    values = {
        name: _mean(
            f"{name}@{k}" if name != "mrr" else "mrr",
            columns[:, i],
            codes,
            rng=rng,
            n_boot=n_boot,
            confidence=confidence,
        )
        for i, name in enumerate(names)
    }
    return RetrievalSummary(k=k, **values)
