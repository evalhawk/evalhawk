"""Streaming alignment and cluster-aware judge-proxy comparisons."""

import math
from array import array
from dataclasses import dataclass, replace
from itertools import groupby

import numpy as np
import numpy.typing as npt

from evalhawk.core.errors import DataError
from evalhawk.core.models import Outcome, Split
from evalhawk.core.protocols import Store
from evalhawk.core.results import Decision, Estimate, ProxyComparison
from evalhawk.services.estimate import representatives
from evalhawk.stats.compare import decide, mcnemar_exact, paired_bootstrap
from evalhawk.stats.paired_correction import corrected_paired_difference
from evalhawk.stats.power import required_n_paired


def compare(
    store: Store,
    *,
    baseline_id: str,
    candidate_id: str,
    criterion_id: str,
    judge_id: str,
    split_set_id: str,
    rng: np.random.Generator,
    tag: str | None = None,
    target_effect: float = 0.05,
    n_boot: int = 2000,
) -> ProxyComparison:
    """Pair by example/repeat; all dependent pairs stay in their locked case cluster."""
    if not math.isfinite(target_effect) or not 0 < target_effect < 1:
        raise DataError("target_effect must be a finite fraction between 0 and 1")
    if baseline_id == candidate_id:
        raise DataError("baseline and candidate must be different executions")

    baseline_values, candidate_values, cluster_values, unmatched, unknown, dependent = _pairs(
        store,
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        criterion_id=criterion_id,
        judge_id=judge_id,
        split_set_id=split_set_id,
        tag=tag,
    )
    difference = paired_bootstrap(
        baseline_values,
        candidate_values,
        rng=rng,
        n_boot=n_boot,
        clusters=cluster_values,
    )
    lost = int(np.count_nonzero((baseline_values == 1) & (candidate_values == 0)))
    gained = int(np.count_nonzero((baseline_values == 0) & (candidate_values == 1)))
    total = None
    warnings = ["Judge-proxy difference, not bias-corrected human-quality improvement."]
    if dependent:
        warnings.append("Dependent pairs: cluster interval; IID McNemar and planning omitted.")
    elif (lost + gained) / len(baseline_values) > target_effect**2:
        total = required_n_paired((lost + gained) / len(baseline_values), target_effect)
        warnings.append("Planning assumes IID pairs, estimated discordance and 80% power.")
    else:
        warnings.append("Discordance too small for the target effect; planning unavailable.")
    if unmatched or unknown:
        warnings.append("Unmatched/UNKNOWN pairs excluded; comparison is conditional.")
    return ProxyComparison(
        difference=replace(difference, unknown_rate=unknown / (unknown + len(baseline_values))),
        decision=decide(difference),
        lost=lost,
        gained=gained,
        p_value=None if dependent else mcnemar_exact(lost, gained),
        unmatched=unmatched,
        unknown_pairs=unknown,
        required_total=total,
        additional_pairs=max(0, total - len(baseline_values)) if total is not None else None,
        warnings=tuple(warnings),
    )


def _pairs(
    store: Store,
    *,
    baseline_id: str,
    candidate_id: str,
    criterion_id: str,
    judge_id: str,
    split_set_id: str,
    tag: str | None,
) -> tuple[
    npt.NDArray[np.int8], npt.NDArray[np.int8], npt.NDArray[np.int32] | None, int, int, bool
]:
    """Align test outcomes by (example, repeat); returns arrays, clusters and exclusions."""

    def rows(run_id: str):
        joined = store.outcome_rows(
            run_id=run_id,
            criterion_id=criterion_id,
            judge_id=judge_id,
            split_set_id=split_set_id,
            split=Split.TEST,
            purpose=f"paired proxy comparison run={run_id} judge={judge_id} tag={tag}",
            tag=tag,
            include_labels=False,
        )
        for _, annotations in groupby(joined, key=lambda row: row.trace_id):
            yield next(annotations)

    baseline = iter(rows(baseline_id))
    candidate = iter(rows(candidate_id))
    left = next(baseline, None)
    right = next(candidate, None)
    values_a = array("b")
    values_b = array("b")
    clusters = array("i")
    codes: dict[tuple[str, str], int] = {}
    unmatched = unknown = 0
    while left is not None or right is not None:
        left_key = (left.example_id, left.repeat_index) if left else None
        right_key = (right.example_id, right.repeat_index) if right else None
        if right_key is None or (left_key is not None and left_key < right_key):
            unmatched += 1
            left = next(baseline, None)
        elif left_key is None or (right_key is not None and right_key < left_key):
            unmatched += 1
            right = next(candidate, None)
        else:
            assert left is not None
            assert right is not None
            if left.group_id != right.group_id:
                raise DataError("paired rows have inconsistent locked groups")
            if Outcome.UNKNOWN in (left.judge, right.judge):
                unknown += 1
            else:
                key = ("group", left.group_id) if left.group_id else ("example", left.example_id)
                code = codes.setdefault(key, len(codes))
                values_a.append(int(left.judge == Outcome.PASS))
                values_b.append(int(right.judge == Outcome.PASS))
                clusters.append(code)
            left = next(baseline, None)
            right = next(candidate, None)
    if len(values_a) < 2:
        raise DataError("need at least two matched pairs with known judgments")
    if len(values_a) < 2:
        raise DataError("need at least two matched pairs with known judgments")
    dependent = len(codes) < len(values_a)
    return (
        np.frombuffer(values_a, dtype=np.int8),
        np.frombuffer(values_b, dtype=np.int8),
        np.frombuffer(clusters, dtype=np.int32) if dependent else None,
        unmatched,
        unknown,
        dependent,
    )


@dataclass(frozen=True, slots=True)
class CorrectedComparison:
    """The bias-corrected v2-v1 difference, its decision, and the uncorrected proxy."""

    difference: Estimate
    decision: Decision
    proxy: Estimate
    calibration_pairs: int
    unmatched: int
    unknown_pairs: int
    warnings: tuple[str, ...]


def corrected_compare(
    store: Store,
    *,
    baseline_id: str,
    candidate_id: str,
    criterion_id: str,
    judge_id: str,
    split_set_id: str,
    rng: np.random.Generator,
    tag: str | None = None,
    n_boot: int = 2000,
) -> CorrectedComparison:
    """Correct the paired judge difference for the judge's errors (true difference = d / J).

    The judge is calibrated on the dev human labels of **both** runs (same judge, same
    criterion), so its sensitivity and specificity are assumed equal for both versions.
    """
    baseline_values, candidate_values, cluster_values, unmatched, unknown, dependent = _pairs(
        store,
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        criterion_id=criterion_id,
        judge_id=judge_id,
        split_set_id=split_set_id,
        tag=tag,
    )
    judges: list[int] = []
    humans: list[int] = []
    for run_id in (baseline_id, candidate_id):
        rows = store.outcome_rows(
            run_id=run_id,
            criterion_id=criterion_id,
            judge_id=judge_id,
            split_set_id=split_set_id,
            split=Split.DEV,
            purpose=f"corrected comparison calibration run={run_id}",
            tag=tag,
            include_labels=True,
        )
        for row, human in representatives(rows):
            if human is None or row.judge_missing or row.judge is Outcome.UNKNOWN:
                continue
            judges.append(int(row.judge is Outcome.PASS))
            humans.append(int(human is Outcome.PASS))
    if len(humans) < 2:
        raise DataError(
            "a corrected comparison needs human labels on dev answers of either version; "
            "label some (evalhawk ui) or compare without --corrected"
        )
    difference = corrected_paired_difference(
        baseline_values,
        candidate_values,
        judges,
        humans,
        rng=rng,
        n_boot=n_boot,
        clusters=cluster_values,
    )
    proxy = paired_bootstrap(
        baseline_values, candidate_values, rng=rng, n_boot=n_boot, clusters=cluster_values
    )
    warnings = [
        "Bias-corrected: judged difference divided by the judge's Youden J (s + c - 1).",
        "Assumes the judge's sensitivity and specificity are the same for both versions.",
    ]
    if dependent:
        warnings.append("Dependent pairs: whole clusters were resampled.")
    if unmatched or unknown:
        warnings.append("Unmatched/UNKNOWN pairs excluded; comparison is conditional.")
    return CorrectedComparison(
        difference=difference,
        decision=decide(difference),
        proxy=proxy,
        calibration_pairs=len(humans),
        unmatched=unmatched,
        unknown_pairs=unknown,
        warnings=tuple(warnings),
    )
