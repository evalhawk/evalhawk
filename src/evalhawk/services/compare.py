"""Streaming alignment and cluster-aware judge-proxy comparisons."""

import math
from array import array
from dataclasses import replace
from itertools import groupby

import numpy as np

from evalhawk.core.errors import DataError
from evalhawk.core.models import Outcome, Split
from evalhawk.core.protocols import Store
from evalhawk.core.results import ProxyComparison
from evalhawk.stats.compare import decide, mcnemar_exact, paired_bootstrap
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
    baseline_values = np.frombuffer(values_a, dtype=np.int8)
    candidate_values = np.frombuffer(values_b, dtype=np.int8)
    dependent = len(codes) < len(values_a)
    cluster_values = np.frombuffer(clusters, dtype=np.int32) if dependent else None
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
    elif (lost + gained) / len(values_a) > target_effect**2:
        total = required_n_paired((lost + gained) / len(values_a), target_effect)
        warnings.append("Planning assumes IID pairs, estimated discordance and 80% power.")
    else:
        warnings.append("Discordance too small for the target effect; planning unavailable.")
    if unmatched or unknown:
        warnings.append("Unmatched/UNKNOWN pairs excluded; comparison is conditional.")
    return ProxyComparison(
        difference=replace(difference, unknown_rate=unknown / (unknown + len(values_a))),
        decision=decide(difference),
        lost=lost,
        gained=gained,
        p_value=None if dependent else mcnemar_exact(lost, gained),
        unmatched=unmatched,
        unknown_pairs=unknown,
        required_total=total,
        additional_pairs=max(0, total - len(values_a)) if total is not None else None,
        warnings=tuple(warnings),
    )
