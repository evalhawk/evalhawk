"""Tune a cheap→strong judge cascade on dev labels."""

from dataclasses import dataclass

import numpy as np

from evalhawk.core.errors import DataError
from evalhawk.core.models import Outcome, Run, Split
from evalhawk.core.protocols import Store
from evalhawk.core.splits import SplitSet
from evalhawk.services.calibrate import run_criteria
from evalhawk.services.estimate import representatives
from evalhawk.stats.selective import (
    CascadeCurve,
    ErrorCorrelation,
    cascade_curve,
    error_correlation,
)


@dataclass(frozen=True, slots=True)
class CascadeAnalysis:
    curve: CascadeCurve
    errors: ErrorCorrelation
    n: int
    skipped_no_probability: int


def _judge_id(run: Run, criterion: str, judge: str) -> tuple[str, str]:
    for item in run_criteria(run):
        if item["name"] == criterion and item["judge"] == judge:
            return item["criterion_id"], item["judge_id"]
    available = ", ".join(f"{i['name']} [{i['judge']}]" for i in run_criteria(run))
    raise DataError(f"run has no judge {judge!r} for {criterion!r}; it has: {available}")


def analyse_cascade(
    store: Store,
    run: Run,
    *,
    criterion: str,
    cheap: str,
    strong: str,
    target_accuracy: float | None = None,
) -> CascadeAnalysis:
    """Risk-coverage curve and error correlation on dev human labels.

    Both judges must have judged the same run (map the criterion to a list of judges,
    e.g. ``criteria = { faithful = ["small", "large"] }``). The cheap judge needs
    probabilities: use ``mode = "verdict_only"`` with a provider that returns logprobs.
    """
    criterion_id, cheap_id = _judge_id(run, criterion, cheap)
    _, strong_id = _judge_id(run, criterion, strong)
    splits = SplitSet.model_validate(run.config_snapshot["splits"])
    rows = store.outcome_rows(
        run_id=run.id,
        criterion_id=criterion_id,
        judge_id=cheap_id,
        split_set_id=splits.id,
        split=Split.DEV,
        purpose="cascade tuning",
        include_labels=True,
    )
    probs: list[float] = []
    strong_out: list[int] = []
    humans: list[int] = []
    skipped = 0
    for row, human in representatives(rows):
        if human is None:
            continue
        cheap_verdict = store.get_verdict(row.trace_id, criterion_id, cheap_id)
        strong_verdict = store.get_verdict(row.trace_id, criterion_id, strong_id)
        if strong_verdict is None or strong_verdict.outcome is Outcome.UNKNOWN:
            continue
        if cheap_verdict is None or cheap_verdict.probability is None:
            skipped += 1
            continue
        probs.append(cheap_verdict.probability)
        strong_out.append(int(strong_verdict.outcome is Outcome.PASS))
        humans.append(int(human is Outcome.PASS))
    if len(humans) < 2:
        hint = (
            ' The cheap judge gave no probabilities: set mode = "verdict_only" on it.'
            if skipped
            else " Label more dev answers (evalhawk ui)."
        )
        raise DataError(f"need at least 2 labelled dev answers judged by both judges.{hint}")
    p = np.asarray(probs)
    h = np.asarray(humans)
    curve = cascade_curve(p, strong_out, h, target_accuracy=target_accuracy)
    errors = error_correlation((p >= 0.5).astype(int), strong_out, h)
    return CascadeAnalysis(
        curve=curve, errors=errors, n=len(humans), skipped_no_probability=skipped
    )
