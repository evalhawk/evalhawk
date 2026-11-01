"""Retrieval quality of a RAG run: hit@k, recall@k, precision@k, MRR, nDCG@k."""

from dataclasses import dataclass

import numpy as np

from evalhawk.core.errors import DataError
from evalhawk.core.models import Run
from evalhawk.core.protocols import Store
from evalhawk.stats.retrieval import RetrievalSummary, retrieval_summary


@dataclass(frozen=True, slots=True)
class RetrievalReport:
    summary: RetrievalSummary
    queries: int
    skipped: int


def run_retrieval(
    store: Store, run: Run, *, k: int, rng: np.random.Generator, n_boot: int = 2000
) -> RetrievalReport:
    """Score repeat-0 answers that have both the dataset's ``relevant_ids`` and the target's
    ``retrieved_ids``; related examples (same ``group_id``) resample together."""
    queries: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    clusters: list[str] = []
    skipped = 0
    for trace in store.iter_traces(run.id):
        if trace.repeat_index != 0:
            continue
        example = store.get_example(trace.example_id)
        if example is None or not example.relevant_ids or trace.retrieved_ids is None:
            skipped += 1
            continue
        queries.append((trace.retrieved_ids, example.relevant_ids))
        clusters.append(example.group_id or example.id)
    if not queries:
        raise DataError(
            "no answers have both relevant_ids (in the dataset) and retrieved_ids (from the "
            "target); add relevant_ids to each row and set retrieved_ids_path on the target"
        )
    summary = retrieval_summary(queries, k=k, rng=rng, clusters=clusters, n_boot=n_boot)
    return RetrievalReport(summary=summary, queries=len(queries), skipped=skipped)
