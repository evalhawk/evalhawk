"""Bias-corrected paired comparison: the true v2-v1 difference behind a judge's verdicts.

If one judge grades both versions with stable sensitivity ``s`` and specificity ``c``,
each version's judged pass rate is ``q = s*theta + (1-c)*(1-theta)``. Subtracting:

    q_candidate - q_baseline = (s + c - 1) * (theta_candidate - theta_baseline)

so the **true difference = judged difference / J**, with Youden's J = s + c - 1. A lenient
or noisy judge (small J) shrinks real differences towards zero; this undoes that.

The interval bootstraps both sources of uncertainty independently: the paired test
differences (resampling whole clusters when given) and the calibration confusion matrix
(multinomial on its four counts), exactly like :func:`corrected_pass_rate`.
"""

import numpy as np
import numpy.typing as npt

from evalhawk.core.errors import JudgeTooWeakError
from evalhawk.core.results import Estimate
from evalhawk.stats._checks import as_binary, check_confidence, check_n_boot, check_same_length
from evalhawk.stats.agreement import confusion
from evalhawk.stats.correction import MIN_YOUDEN

_BATCH = 128


def _cluster_sums(
    diff: npt.NDArray[np.float64], clusters: npt.ArrayLike | None
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    if clusters is None:
        return diff, np.ones_like(diff)
    labels = np.asarray(clusters)
    check_same_length("clusters", labels, "pairs", diff)
    _, codes = np.unique(labels, return_inverse=True)
    if codes.max() < 1:
        raise ValueError("clusters must contain at least two distinct clusters")
    sums = np.bincount(codes, weights=diff)
    sizes = np.bincount(codes).astype(np.float64)
    return sums, sizes


def corrected_paired_difference(
    baseline: npt.ArrayLike,
    candidate: npt.ArrayLike,
    judge_cal: npt.ArrayLike,
    human_cal: npt.ArrayLike,
    *,
    rng: np.random.Generator,
    n_boot: int = 2000,
    confidence: float = 0.95,
    clusters: npt.ArrayLike | None = None,
) -> Estimate:
    """Corrected ``theta_candidate - theta_baseline`` with a two-source bootstrap interval.

    Args:
        baseline, candidate: The judge's 0/1 verdicts on the same test items (paired).
        judge_cal, human_cal: Judge and human 0/1 labels on the calibration set.
        rng: Random generator for resampling.
        n_boot: Bootstrap resamples (>= 100).
        confidence: Interval level.
        clusters: Optional cluster label per pair (related items resample together).

    Returns:
        An Estimate in [-1, 1] with method ``"paired_rogan_gladen+bootstrap"``.

    Raises:
        ValueError: on invalid inputs, or calibration without both PASS and FAIL labels.
        JudgeTooWeakError: if J <= MIN_YOUDEN, or more than 1% of resamples degenerate.
    """
    check_confidence(confidence)
    check_n_boot(n_boot)
    a = as_binary("baseline", baseline)
    b = as_binary("candidate", candidate)
    check_same_length("baseline", a, "candidate", b)
    judge = as_binary("judge_cal", judge_cal)
    human = as_binary("human_cal", human_cal)
    check_same_length("judge_cal", judge, "human_cal", human)
    if not (human == 1).any() or not (human == 0).any():
        raise ValueError(
            "calibration needs both PASS and FAIL human labels to estimate the judge's errors"
        )
    matrix = confusion(human, judge)
    s_obs = matrix.tp / (matrix.tp + matrix.fn)
    c_obs = matrix.tn / (matrix.tn + matrix.fp)
    youden = s_obs + c_obs - 1
    if youden <= MIN_YOUDEN:
        raise JudgeTooWeakError(
            f"judge too weak to correct a comparison: sensitivity + specificity - 1 = "
            f"{youden:.3f} <= {MIN_YOUDEN}; improve the judge or compare judged rates only"
        )
    diff = (b - a).astype(np.float64)
    point = float(np.clip(diff.mean() / youden, -1.0, 1.0))

    sums, sizes = _cluster_sums(diff, clusters)
    groups = sums.size
    d_r = np.empty(n_boot)
    for start in range(0, n_boot, _BATCH):
        stop = min(start + _BATCH, n_boot)
        picks = rng.integers(0, groups, size=(stop - start, groups))
        d_r[start:stop] = sums[picks].sum(axis=1) / sizes[picks].sum(axis=1)
    cells = np.array([matrix.tp, matrix.fn, matrix.fp, matrix.tn], dtype=np.int64)
    tp, fn, fp, tn = rng.multinomial(human.size, cells / human.size, size=n_boot).astype(float).T
    with np.errstate(divide="ignore", invalid="ignore"):
        j_r = tp / (tp + fn) + tn / (tn + fp) - 1
        theta_r = np.clip(d_r / j_r, -1.0, 1.0)
    valid = (tp + fn > 0) & (tn + fp > 0) & (j_r > 0)
    dropped = n_boot - int(valid.sum())
    if dropped / n_boot > 0.01:
        raise JudgeTooWeakError(
            f"bootstrap interval unreliable: {dropped} / {n_boot} resamples have a "
            f"degenerate judge calibration; label more examples of both outcomes"
        )
    low, high = np.quantile(theta_r[valid], [(1 - confidence) / 2, (1 + confidence) / 2])
    low, high = min(float(low), point), max(float(high), point)
    return Estimate(
        point=point,
        low=low,
        high=high,
        n=int(a.size),
        method="paired_rogan_gladen+bootstrap",
        confidence=confidence,
    )
