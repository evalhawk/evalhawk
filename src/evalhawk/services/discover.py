"""Failure discovery: cluster why answers failed, to suggest new criteria."""

from dataclasses import dataclass

import numpy as np

from evalhawk.clustering.text import Cluster, cluster_texts
from evalhawk.core.errors import DataError
from evalhawk.core.models import Outcome, Run
from evalhawk.core.protocols import Store
from evalhawk.services.calibrate import run_criteria


@dataclass(frozen=True, slots=True)
class FailureText:
    source: str  # "judge" or "human"
    criterion: str
    text: str


def failure_texts(store: Store, run: Run, *, criterion: str | None = None) -> list[FailureText]:
    """Judge reasoning on FAIL verdicts and human notes on FAIL labels, for a run.

    Reading verdicts here is not a test-pile *estimate*; it is a qualitative error
    analysis, and its results must not be used to tune a judge evaluated on test.
    """
    entries = [e for e in run_criteria(run) if criterion is None or e["name"] == criterion]
    if not entries:
        raise DataError(f"run has no criterion {criterion!r}")
    out: list[FailureText] = []
    for trace in store.iter_traces(run.id):
        for entry in entries:
            verdict = store.get_verdict(trace.id, entry["criterion_id"], entry["judge_id"])
            if verdict is not None and verdict.outcome is Outcome.FAIL and verdict.reasoning:
                out.append(FailureText("judge", entry["name"], verdict.reasoning))
        for label in store.labels_for(trace.id):
            if label.outcome is Outcome.FAIL and label.note:
                names = [e["name"] for e in entries if e["criterion_id"] == label.criterion_id]
                if names:
                    out.append(FailureText("human", names[0], label.note))
    return out


def discover(
    store: Store, run: Run, *, criterion: str | None = None, k: int | None = None, seed: int = 0
) -> tuple[list[Cluster], list[FailureText]]:
    """Cluster the failure texts; each cluster is a candidate failure mode."""
    texts = failure_texts(store, run, criterion=criterion)
    if len(texts) < 2:
        raise DataError(
            "need at least 2 failure reasons: FAIL verdicts with reasoning (LLM judges in "
            "reason_then_verdict mode) or FAIL labels with notes"
        )
    clusters = cluster_texts([t.text for t in texts], k=k, rng=np.random.default_rng(seed))
    return clusters, texts
