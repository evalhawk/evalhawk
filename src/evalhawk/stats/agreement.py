"""Judge agreement metrics: sensitivity, specificity, and Cohen's kappa.

This module computes how well a judge agrees with a human rater. PASS is the
positive class; see §13.1 of the architecture for the naming convention.

Sensitivity = TP / (TP + FN) = recall of the PASS class.
Specificity = TN / (TN + FP) = recall of the FAIL class.

Cohen's kappa measures agreement beyond chance. The formula is:
    κ = (p_o − p_e) / (1 − p_e)
where p_o is observed agreement and p_e is expected agreement by chance.

References:
    - Cohen, J. (1960). "A coefficient of agreement for nominal scales."
      Educational and Psychological Measurement, 20(1), 37–46.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from evalhawk.core.results import Estimate
from evalhawk.stats._checks import (
    as_binary,
    check_confidence,
    check_n_boot,
    check_same_length,
)
from evalhawk.stats.intervals import wilson_interval


@dataclass(frozen=True, slots=True, kw_only=True)
class Confusion:
    """2×2 confusion matrix for binary classification.

    Attributes:
        tp: True positives (human PASS, judge PASS). Must be >= 0.
        fn: False negatives (human PASS, judge FAIL). Must be >= 0.
        fp: False positives (human FAIL, judge PASS). Must be >= 0.
        tn: True negatives (human FAIL, judge FAIL). Must be >= 0.

    Invariants:
        - All fields are non-negative integers.
        - Total (tp + fn + fp + tn) >= 1.
    """

    tp: int
    fn: int
    fp: int
    tn: int

    def __post_init__(self) -> None:
        """Validate confusion matrix fields."""
        if self.tp < 0:
            raise ValueError(f"tp must be >= 0, got {self.tp!r}")
        if self.fn < 0:
            raise ValueError(f"fn must be >= 0, got {self.fn!r}")
        if self.fp < 0:
            raise ValueError(f"fp must be >= 0, got {self.fp!r}")
        if self.tn < 0:
            raise ValueError(f"tn must be >= 0, got {self.tn!r}")

        total = self.tp + self.fn + self.fp + self.tn
        if total < 1:
            raise ValueError(
                f"Confusion total must be >= 1, got tp={self.tp}, fn={self.fn}, "
                f"fp={self.fp}, tn={self.tn} (total={total})"
            )

    @property
    def n(self) -> int:
        """Total number of items (pairs)."""
        return self.tp + self.fn + self.fp + self.tn


def confusion(human: npt.ArrayLike, judge: npt.ArrayLike) -> Confusion:
    """Compute the 2×2 confusion matrix.

    Args:
        human: Human labels. Must be 1-D, non-empty, and contain only 0/1.
        judge: Judge labels. Must be 1-D, non-empty, and contain only 0/1.

    Returns:
        A Confusion object with tp, fn, fp, tn counts.

    Raises:
        ValueError: If lengths don't match, or if arrays are invalid.
    """
    human_arr = as_binary("human", human)
    judge_arr = as_binary("judge", judge)
    check_same_length("human", human_arr, "judge", judge_arr)

    tp = int(np.count_nonzero((human_arr == 1) & (judge_arr == 1)))
    fn = int(np.count_nonzero((human_arr == 1) & (judge_arr == 0)))
    fp = int(np.count_nonzero((human_arr == 0) & (judge_arr == 1)))
    tn = int(np.count_nonzero((human_arr == 0) & (judge_arr == 0)))

    return Confusion(tp=tp, fn=fn, fp=fp, tn=tn)


def sensitivity(c: Confusion, *, confidence: float = 0.95) -> Estimate:
    """Sensitivity (recall of the PASS class).

    Sensitivity = TP / (TP + FN).

    Args:
        c: Confusion matrix.
        confidence: Confidence level (e.g., 0.95 for 95%). Defaults to 0.95.

    Returns:
        An Estimate with the point estimate, interval bounds, and metadata.

    Raises:
        ValueError: If TP + FN == 0 (no human PASS items).
    """
    check_confidence(confidence)

    n_pass = c.tp + c.fn
    if n_pass == 0:
        raise ValueError(
            "human_cal has no PASS items, so sensitivity is undefined; label more passing examples"
        )

    return wilson_interval(c.tp, n_pass, confidence=confidence)


def specificity(c: Confusion, *, confidence: float = 0.95) -> Estimate:
    """Specificity (recall of the FAIL class).

    Specificity = TN / (TN + FP).

    Args:
        c: Confusion matrix.
        confidence: Confidence level (e.g., 0.95 for 95%). Defaults to 0.95.

    Returns:
        An Estimate with the point estimate, interval bounds, and metadata.

    Raises:
        ValueError: If TN + FP == 0 (no human FAIL items).
    """
    check_confidence(confidence)

    n_fail = c.tn + c.fp
    if n_fail == 0:
        raise ValueError(
            "human_cal has no FAIL items, so specificity is undefined; label more failing examples"
        )

    return wilson_interval(c.tn, n_fail, confidence=confidence)


def cohen_kappa(
    human: npt.ArrayLike,
    judge: npt.ArrayLike,
    *,
    rng: np.random.Generator,
    n_boot: int = 2000,
    confidence: float = 0.95,
) -> Estimate:
    """Cohen's kappa: agreement beyond chance.

    Kappa measures agreement corrected for chance:
        κ = (p_o − p_e) / (1 − p_e)

    where p_o = (TP + TN) / n and p_e is expected agreement by chance.

    The interval is computed via percentile bootstrap: resample counts using
    multinomial and recompute κ for each resample. Degenerate resamples
    (p_e == 1) are dropped; if > 1% are dropped, raise ValueError.

    Args:
        human: Human labels. Must be 1-D, non-empty, and contain only 0/1.
        judge: Judge labels. Must be 1-D, non-empty, and contain only 0/1.
        rng: NumPy random generator for resampling.
        n_boot: Number of bootstrap resamples. Must be >= 100. Defaults to 2000.
        confidence: Confidence level (e.g., 0.95 for 95%). Defaults to 0.95.

    Returns:
        An Estimate with the point estimate, interval bounds, and metadata.

    Raises:
        ValueError: If observed p_e == 1, or if > 1% of resamples degenerate.
    """
    check_confidence(confidence)
    check_n_boot(n_boot)

    human_arr = as_binary("human", human)
    judge_arr = as_binary("judge", judge)
    check_same_length("human", human_arr, "judge", judge_arr)

    c = confusion(human_arr, judge_arr)
    n = c.n

    p_o = (c.tp + c.tn) / n
    p_margin_pass = (c.tp + c.fn) / n
    p_margin_judge_pass = (c.tp + c.fp) / n
    p_margin_fail = (c.tn + c.fp) / n
    p_margin_judge_fail = (c.fn + c.tn) / n
    p_e = p_margin_pass * p_margin_judge_pass + p_margin_fail * p_margin_judge_fail

    if p_e >= 1.0:
        raise ValueError(
            "both raters constant and identical, so expected agreement is 1 and kappa is undefined"
        )

    observed_kappa = (p_o - p_e) / (1 - p_e)

    counts = np.array([c.tp, c.fn, c.fp, c.tn], dtype=np.int64)
    resamples = rng.multinomial(n, counts / n, size=n_boot).astype(np.float64)
    tp_r, fn_r, fp_r, tn_r = resamples.T
    p_o_r = (tp_r + tn_r) / n
    p_e_r = ((tp_r + fn_r) * (tp_r + fp_r) + (tn_r + fp_r) * (fn_r + tn_r)) / (n * n)

    valid = p_e_r < 1.0
    n_dropped = n_boot - int(valid.sum())
    if n_dropped > 0:
        drop_rate = n_dropped / n_boot
        if drop_rate > 0.01:
            raise ValueError(
                f"bootstrap interval unreliable: {n_dropped} / {n_boot} "
                f"({drop_rate:.1%}) resamples degenerate; label more examples"
            )

    kappas = (p_o_r[valid] - p_e_r[valid]) / (1 - p_e_r[valid])
    low, high = np.quantile(kappas, [(1 - confidence) / 2, (1 + confidence) / 2])

    return Estimate(
        point=observed_kappa,
        low=float(low),
        high=float(high),
        n=n,
        method="cohen_kappa+bootstrap",
        confidence=confidence,
    )
