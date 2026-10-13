"""Reduce stored scalar outcomes into independent representative-case statistics."""

from array import array
from collections.abc import Iterable, Iterator
from dataclasses import replace
from itertools import chain, groupby

import numpy as np
import numpy.typing as npt

from evalhawk.core.errors import DataError
from evalhawk.core.models import Outcome, Split
from evalhawk.core.protocols import OutcomeRow, Store
from evalhawk.core.results import Report
from evalhawk.stats.agreement import cohen_kappa, confusion, sensitivity, specificity
from evalhawk.stats.correction import corrected_pass_rate, ppi_mean
from evalhawk.stats.intervals import wilson_interval


def adjudicate(rows: Iterable[OutcomeRow]) -> Outcome | None:
    """Latest per annotator, then majority of known votes; equal-time conflicts abstain."""
    latest: dict[str, OutcomeRow] = {}
    conflicts: set[str] = set()
    for row in rows:
        if row.annotator is None or row.label_time is None:
            continue
        if row.inclusion_prob != 1:
            raise DataError(
                "label sampling requires weighted inference; use inclusion probability 1"
            )
        previous = latest.get(row.annotator)
        if previous is None or previous.label_time is None or row.label_time > previous.label_time:
            latest[row.annotator] = row
            conflicts.discard(row.annotator)
        elif row.label_time == previous.label_time and row.human != previous.human:
            conflicts.add(row.annotator)
    votes = sum(
        1 if row.human == Outcome.PASS else -1
        for annotator, row in latest.items()
        if annotator not in conflicts and row.human in (Outcome.PASS, Outcome.FAIL)
    )
    return Outcome.PASS if votes > 0 else Outcome.FAIL if votes < 0 else None


def representatives(
    rows: Iterable[OutcomeRow],
    *,
    adjudicate_labels: bool = True,
) -> Iterator[tuple[OutcomeRow, Outcome | None]]:
    """Choose by identifiers before outcomes, using the locked group snapshot."""
    seen: set[tuple[str, str]] = set()
    for _, annotations in groupby(rows, key=lambda item: item.trace_id):
        stream = chain(annotations)
        first = next(stream)
        key = ("group", first.group_id) if first.group_id else ("example", first.example_id)
        if key in seen:
            continue
        seen.add(key)
        if first.repeat_index != 0:
            continue
        yield first, adjudicate(chain((first,), stream)) if adjudicate_labels else None


def report(
    store: Store,
    *,
    run_id: str,
    criterion_id: str,
    judge_id: str,
    split_set_id: str,
    rng: np.random.Generator,
    tag: str | None = None,
    n_boot: int = 2000,
) -> Report:
    """Dev calibration and audited test prediction for the fixed representative population."""
    judges = array("b")
    humans = array("b")
    predictions = array("b")
    dev_cases = unresolved = dev_unknown = test_cases = test_unknown = 0
    dev_missing = test_missing = 0
    for pile in (Split.DEV, Split.TEST):
        rows = store.outcome_rows(
            run_id=run_id,
            criterion_id=criterion_id,
            judge_id=judge_id,
            split_set_id=split_set_id,
            split=pile,
            purpose=f"rate report run={run_id} criterion={criterion_id} judge={judge_id} tag={tag}",
            tag=tag,
            include_labels=pile == Split.DEV,
        )
        for row, human in representatives(rows, adjudicate_labels=pile == Split.DEV):
            if pile == Split.DEV:
                dev_cases += 1
                unresolved += human is None
                dev_unknown += row.judge == Outcome.UNKNOWN
                dev_missing += row.judge_missing
                if human is not None and row.judge != Outcome.UNKNOWN:
                    judges.append(int(row.judge == Outcome.PASS))
                    humans.append(int(human == Outcome.PASS))
            else:
                test_cases += 1
                test_unknown += row.judge == Outcome.UNKNOWN
                test_missing += row.judge_missing
                if row.judge != Outcome.UNKNOWN:
                    predictions.append(int(row.judge == Outcome.PASS))
    if len(judges) < 2 or len(predictions) < 2:
        raise DataError("need at least two resolved dev pairs and two known test representatives")
    judge_cal: npt.NDArray[np.int8] = np.frombuffer(judges, dtype=np.int8)
    human_cal: npt.NDArray[np.int8] = np.frombuffer(humans, dtype=np.int8)
    judge_test: npt.NDArray[np.int8] = np.frombuffer(predictions, dtype=np.int8)
    matrix = confusion(human_cal, judge_cal)
    unknown_rate = test_unknown / test_cases
    naive = wilson_interval(int(judge_test.sum()), judge_test.size)
    corrected = corrected_pass_rate(judge_test, judge_cal, human_cal, rng=rng, n_boot=n_boot)
    ppi = ppi_mean(human_cal, judge_cal, judge_test)
    return Report(
        naive=replace(naive, unknown_rate=unknown_rate),
        corrected=replace(corrected, unknown_rate=unknown_rate),
        ppi=replace(ppi, unknown_rate=unknown_rate),
        sensitivity=sensitivity(matrix),
        specificity=specificity(matrix),
        kappa=cohen_kappa(human_cal, judge_cal, rng=rng, n_boot=n_boot),
        dev_cases=dev_cases,
        calibration_pairs=len(judges),
        unresolved_labels=unresolved,
        dev_unknown=dev_unknown,
        test_cases=test_cases,
        dev_missing=dev_missing,
        test_missing=test_missing,
        warnings=(
            "Estimand: fixed representative per locked case, repeat 0; not all paraphrases.",
            "Assumes independent cases, representative resolved labels and stable judge errors.",
            "UNKNOWN judgments and unresolved labels are excluded; rates are conditional.",
            "Tag reports recalibrate within the tag; intervals are not multiplicity-adjusted.",
        ),
    )
