"""Rogan-Gladen correction for judge miscalibration (card S3).

The Rogan-Gladen correction accounts for a judge's known miscalibration using
its sensitivity s and specificity c to correct an observed pass rate q:

    θ = (q + c − 1) / (s + c − 1)

The formula is inverted from the confusion matrix equation q = s·θ + (1−c)(1−θ).
When the judge's Youden's J = s + c − 1 is too small (barely better than random),
correction amplifies noise; use rogan_gladen() to validate before correcting.

Uncertainty comes from both the calibration set (estimating s, c) and the test set
(estimating q), so corrected_pass_rate() bootstraps both independently.

Assumptions:
- The judge's error rates (sensitivity, specificity) are the same on the
  calibration and test sets (e.g., the distribution does not shift).

References:
    - Rogan, W. J., & Gladen, B. (1978). "Estimating prevalence from the results
      of a screening test." American Journal of Epidemiology, 107(1), 71–76.
    - "How to Correctly Report LLM-as-a-Judge Evaluations." arXiv:2511.21140.
      (Method section: bootstrap intervals for the Rogan-Gladen correction.)
"""

import math
from typing import Final

import numpy as np
import numpy.typing as npt

from evalhawk.core.errors import JudgeTooWeakError
from evalhawk.core.results import Estimate
from evalhawk.stats._checks import (
    as_binary,
    check_confidence,
    check_n_boot,
    check_same_length,
    z_value,
)
from evalhawk.stats.agreement import confusion
from evalhawk.stats.clustered import cluster_bootstrap_means

MIN_YOUDEN: Final = 0.1
"""Minimum Youden's J = s + c − 1 to attempt correction.

If J <= MIN_YOUDEN, the judge is barely better than random and correction
would amplify noise. Raise JudgeTooWeakError instead.
"""


def rogan_gladen(q: float, sensitivity: float, specificity: float) -> float:
    """Rogan-Gladen correction: adjust observed pass rate for judge miscalibration.

    Given an observed pass rate q and a judge's sensitivity s (recall of PASS)
    and specificity c (recall of FAIL), corrects q for the judge's known
    miscalibration using:

        θ = (q + c − 1) / (s + c − 1)

    The denominator is Youden's J (a measure of the judge's utility). If J <= 0.1,
    the judge is barely better than random and correction would amplify noise.

    The result is clipped to [0, 1]:
    - If q < 1 − c, return 0 (judge's false positive rate too high).
    - If q > s, return 1 (judge's false negative rate too high).

    Args:
        q: Observed pass rate of the judge on the test set. Must be finite in [0, 1].
        sensitivity: Judge's sensitivity = TP / (TP + FN). Must be finite in [0, 1].
        specificity: Judge's specificity = TN / (TN + FP). Must be finite in [0, 1].

    Returns:
        The corrected pass rate θ, clipped to [0, 1].

    Raises:
        ValueError: If any parameter is not finite or not in [0, 1].
        JudgeTooWeakError: If s + c − 1 <= MIN_YOUDEN (judge barely better than random).
    """
    # Validate inputs: finite and in [0, 1]
    if not math.isfinite(q):
        raise ValueError(f"q must be finite, got {q!r}")
    if not (0 <= q <= 1):
        raise ValueError(f"q must be in [0, 1], got {q!r}")

    if not math.isfinite(sensitivity):
        raise ValueError(f"sensitivity must be finite, got {sensitivity!r}")
    if not (0 <= sensitivity <= 1):
        raise ValueError(f"sensitivity must be in [0, 1], got {sensitivity!r}")

    if not math.isfinite(specificity):
        raise ValueError(f"specificity must be finite, got {specificity!r}")
    if not (0 <= specificity <= 1):
        raise ValueError(f"specificity must be in [0, 1], got {specificity!r}")

    # Check Youden's J (tolerance: 0.6 + 0.5 - 1 is 0.10000000000000009 in floats)
    youden = sensitivity + specificity - 1
    if youden <= MIN_YOUDEN + 1e-12:
        raise JudgeTooWeakError(
            f"judge too weak to correct: observed sensitivity={sensitivity:.4f}, "
            f"specificity={specificity:.4f}, Youden's J={youden:.4f} <= {MIN_YOUDEN}; "
            f"barely better than random; correcting would amplify noise; "
            f"improve the judge or its prompt"
        )

    # Apply formula θ = (q + c − 1) / (s + c − 1), then clip to [0, 1]
    theta = (q + specificity - 1) / youden
    return float(np.clip(theta, 0.0, 1.0))


def corrected_pass_rate(
    judge_test: npt.ArrayLike,
    judge_cal: npt.ArrayLike,
    human_cal: npt.ArrayLike,
    *,
    rng: np.random.Generator,
    n_boot: int = 2000,
    confidence: float = 0.95,
    test_clusters: npt.ArrayLike | None = None,
) -> Estimate:
    """Correct a judge's observed pass rate for miscalibration using bootstrap.

    Estimates the true pass rate θ using Rogan-Gladen correction, accounting for
    uncertainty in both the judge's calibration (sensitivity s, specificity c) and
    the observed test pass rate q. Bootstraps independently over the calibration
    confusion matrix (via multinomial on the 2×2 counts) and the test pass rate
    (via binomial on the pass count, or cluster bootstrap if test_clusters given).

    When test_clusters is provided, resamples cluster indices instead of individual
    test items, accounting for within-cluster correlation (e.g., multiple items
    from the same document).

    Assumptions:
    - The judge's error rates (sensitivity, specificity) are stable across the
      calibration and test sets (no distribution shift).
    - Binary labels only (0 = FAIL, 1 = PASS).

    Args:
        judge_test: Judge's labels on the test set. Must be binary (0/1).
        judge_cal: Judge's labels on the calibration set. Must be binary (0/1).
        human_cal: Human's labels on the calibration set. Must be binary (0/1).
        rng: NumPy random generator for resampling. Never seeded inside this function.
        n_boot: Number of bootstrap resamples. Must be >= 100. Defaults to 2000.
        confidence: Confidence level for the interval, e.g., 0.95 for 95%.
            Defaults to 0.95.
        test_clusters: Optional cluster labels for test set. When provided,
            resamples cluster indices instead of individual test items.
            Must have >= 2 unique clusters. Defaults to None (iid resampling).

    Returns:
        An Estimate with:
        - point: Observed point estimate (rogan_gladen(q, s, c)).
        - low, high: Percentile interval from bootstrap resamples.
        - n: Length of judge_test (P5).
        - method: "rogan_gladen+bootstrap".
        - confidence: As specified.

    Raises:
        ValueError: If inputs are invalid (not binary, empty, mismatched lengths),
            or if human_cal lacks both PASS and FAIL examples (P4), or if > 1% of
            bootstrap resamples degenerate (P3). If test_clusters is given, also
            raises if test_clusters and judge_test have different lengths or if
            there is only one cluster.
        JudgeTooWeakError: If observed Youden's J <= MIN_YOUDEN (P4), or if > 1%
            of resamples degenerate due to weak judge (P3).
    """
    # Validate inputs
    check_confidence(confidence)
    check_n_boot(n_boot)

    judge_test_arr = as_binary("judge_test", judge_test)
    judge_cal_arr = as_binary("judge_cal", judge_cal)
    human_cal_arr = as_binary("human_cal", human_cal)

    if judge_test_arr.size == 0:
        raise ValueError("judge_test must be non-empty")

    check_same_length("judge_cal", judge_cal_arr, "human_cal", human_cal_arr)

    # Validate calibration has both classes (P4)
    if not np.any(human_cal_arr == 1):
        raise ValueError(
            "human_cal has no PASS items (no 1s), so sensitivity is undefined; "
            "label more passing examples"
        )
    if not np.any(human_cal_arr == 0):
        raise ValueError(
            "human_cal has no FAIL items (no 0s), so specificity is undefined; "
            "label more failing examples"
        )

    n_test = judge_test_arr.size
    n_cal = judge_cal_arr.size

    # Compute observed statistics
    c = confusion(human_cal_arr, judge_cal_arr)
    s_obs = c.tp / (c.tp + c.fn) if (c.tp + c.fn) > 0 else 0.0
    c_obs = c.tn / (c.tn + c.fp) if (c.tn + c.fp) > 0 else 0.0
    q_obs = float(np.mean(judge_test_arr))

    # Compute point estimate (this validates and may raise JudgeTooWeakError)
    point = rogan_gladen(q_obs, s_obs, c_obs)

    # Bootstrap: resample calibration counts and the test pass rate
    cells = np.array([c.tp, c.fn, c.fp, c.tn], dtype=np.int64)
    resamples = rng.multinomial(n_cal, cells / n_cal, size=n_boot).astype(np.float64)
    tp_r, fn_r, fp_r, tn_r = resamples.T

    if test_clusters is None:
        q_r = rng.binomial(n_test, q_obs, size=n_boot) / n_test
    else:
        q_r = cluster_bootstrap_means(judge_test_arr, test_clusters, rng=rng, n_boot=n_boot)

    # Degenerate resamples give NaN or non-positive Youden's J and are dropped (P3)
    with np.errstate(divide="ignore", invalid="ignore"):
        s_r = tp_r / (tp_r + fn_r)
        c_r = tn_r / (tn_r + fp_r)
        youden_r = s_r + c_r - 1
        theta_r = np.clip((q_r + c_r - 1) / youden_r, 0.0, 1.0)

    valid = (tp_r + fn_r > 0) & (tn_r + fp_r > 0) & (youden_r > 0)
    n_dropped = n_boot - int(valid.sum())
    if n_dropped > 0:
        drop_rate = n_dropped / n_boot
        if drop_rate > 0.01:
            raise JudgeTooWeakError(
                f"bootstrap interval unreliable: {n_dropped} / {n_boot} "
                f"({drop_rate:.1%}) resamples degenerate (judge too weak); "
                f"improve the judge or its prompt or label more examples"
            )

    # Compute percentile interval (P2)
    low, high = np.quantile(theta_r[valid], [(1 - confidence) / 2, (1 + confidence) / 2])

    return Estimate(
        point=point,
        low=float(low),
        high=float(high),
        n=n_test,
        method="rogan_gladen+bootstrap",
        confidence=confidence,
    )


def ppi_mean(
    y_labeled: npt.ArrayLike,
    yhat_labeled: npt.ArrayLike,
    yhat_unlabeled: npt.ArrayLike,
    *,
    confidence: float = 0.95,
) -> Estimate:
    """Prediction-powered inference (PPI) for mean estimation.

    Measure the judge's average error on a small labeled set (the rectifier) and
    subtract it from the judge's average on a large unlabeled set. This gives an
    unbiased estimate of the true mean regardless of the judge's quality; a good
    judge just gives a narrower interval.

    The formula is:
        rectifier = mean(ŷ_labeled − y_labeled)
        θ̂ = mean(ŷ_unlabeled) − rectifier
        Var ≈ Var(ŷ_unlabeled) / N + Var(ŷ_labeled − y_labeled) / n
        low, high = θ̂ ∓ z · √Var

    Bounds are not clipped to [0, 1], preserving oracle agreement. For binary data
    they may slightly exceed the bounds.

    Assumption: the labeled set is a random sample of the same population as the
    unlabeled set.

    Args:
        y_labeled: Human labels (ground truth) on the small labeled set.
            Must be 1-D array of finite floats; probabilities allowed, not only 0/1.
            Length n must be >= 2.
        yhat_labeled: Judge predictions on the labeled set. Must be same length
            as y_labeled and contain finite floats.
        yhat_unlabeled: Judge predictions on the large unlabeled set. Must be 1-D
            array of finite floats with length N >= 2.
        confidence: Confidence level (e.g., 0.95 for 95%). Must be in (0, 1).
            Defaults to 0.95.

    Returns:
        An Estimate with the point estimate θ̂, interval bounds [low, high],
        n = N (size of unlabeled set), method="ppi", and the given confidence.

    Raises:
        ValueError: If arrays are not 1-D, contain non-finite values, have
            mismatched lengths, or have n < 2 or N < 2.

    References:
        - Angelopoulos, A., Bates, S., Candès, E. J., Malik, J., & Jordan, M. I.
          (2023). "Prediction-powered inference." Science, 382(6671), 669–674.
          https://doi.org/10.1126/science.adi6000
    """
    # Validate and convert inputs
    check_confidence(confidence)

    y_arr = np.asarray(y_labeled)
    yhat_arr = np.asarray(yhat_labeled)
    yhat_unl_arr = np.asarray(yhat_unlabeled)

    # Check 1-D
    if y_arr.ndim != 1:
        raise ValueError(
            f"y_labeled must be 1-D, got {y_arr.ndim}-D array of shape {y_arr.shape!r}"
        )
    if yhat_arr.ndim != 1:
        raise ValueError(
            f"yhat_labeled must be 1-D, got {yhat_arr.ndim}-D array of shape {yhat_arr.shape!r}"
        )
    if yhat_unl_arr.ndim != 1:
        raise ValueError(
            f"yhat_unlabeled must be 1-D, got {yhat_unl_arr.ndim}-D array "
            f"of shape {yhat_unl_arr.shape!r}"
        )

    # Check finite
    if not np.all(np.isfinite(y_arr)):
        raise ValueError(
            f"y_labeled must be finite floats, got values with non-finite: "
            f"{y_arr[~np.isfinite(y_arr)]!r}"
        )
    if not np.all(np.isfinite(yhat_arr)):
        raise ValueError(
            f"yhat_labeled must be finite floats, got values with non-finite: "
            f"{yhat_arr[~np.isfinite(yhat_arr)]!r}"
        )
    if not np.all(np.isfinite(yhat_unl_arr)):
        raise ValueError(
            f"yhat_unlabeled must be finite floats, got values with non-finite: "
            f"{yhat_unl_arr[~np.isfinite(yhat_unl_arr)]!r}"
        )

    # Check same length
    check_same_length("y_labeled", y_arr, "yhat_labeled", yhat_arr)

    n = len(y_arr)
    n_unlabeled = len(yhat_unl_arr)

    # Check n >= 2
    if n < 2:
        raise ValueError(f"n must be >= 2, got {n!r}")

    # Check N >= 2
    if n_unlabeled < 2:
        raise ValueError(f"N must be >= 2, got {n_unlabeled!r}")

    # Convert to float64 for computation
    y_arr = np.asarray(y_arr, dtype=np.float64)
    yhat_arr = np.asarray(yhat_arr, dtype=np.float64)
    yhat_unl_arr = np.asarray(yhat_unl_arr, dtype=np.float64)

    # Compute rectifier: mean(ŷ_labeled − y_labeled)
    rectifier = np.mean(yhat_arr - y_arr)

    # Compute point estimate: θ = mean(ŷ_unlabeled) - rectifier
    theta = np.mean(yhat_unl_arr) - rectifier

    # Compute standard errors (using ddof=0, population std, to match ppi_py)
    var_unlabeled = np.var(yhat_unl_arr, ddof=0)
    var_rectifier = np.var(yhat_arr - y_arr, ddof=0)

    # Compute pooled standard error
    se_sq = var_unlabeled / n_unlabeled + var_rectifier / n
    se = math.sqrt(se_sq)

    # Compute z-score for confidence level
    z = z_value(confidence)

    # Compute bounds (not clipped)
    low = theta - z * se
    high = theta + z * se

    return Estimate(
        point=float(theta),
        low=float(low),
        high=float(high),
        n=n_unlabeled,
        method="ppi",
        confidence=confidence,
    )
