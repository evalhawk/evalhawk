"""Selective prediction for judge cascades: when to trust a cheap judge.

A cascade accepts the cheap judge's verdict when it is confident, and escalates to a
strong judge otherwise. With cheap probability ``p = P(PASS)`` and threshold ``tau`` in
[0.5, 1]: accept PASS if ``p >= tau``, accept FAIL if ``p <= 1 - tau``, else escalate.

* **coverage**: the share of items the cheap judge decides by itself (cost saved).
* **accuracy**: agreement of the combined verdicts with human labels.

Sweeping ``tau`` traces a risk-coverage curve. Choose ``tau`` on **dev** labels, then
measure on test. A cascade only helps if the strong judge is right where the cheap one
is wrong: :func:`error_correlation` compares ``P(strong wrong | cheap wrong)`` with
``P(strong wrong)`` ("Cheaper, Faster, and Wrong in the Same Places", 2026).
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from evalhawk.core.results import Estimate
from evalhawk.stats._checks import as_binary, check_same_length
from evalhawk.stats.intervals import wilson_interval


@dataclass(frozen=True, slots=True)
class CascadePoint:
    """One threshold on the risk-coverage curve."""

    threshold: float
    coverage: float
    accuracy: Estimate
    escalations: int


@dataclass(frozen=True, slots=True)
class CascadeCurve:
    """The full curve, the reference accuracies, and the chosen threshold (if any)."""

    points: tuple[CascadePoint, ...]
    cheap_accuracy: Estimate
    strong_accuracy: Estimate
    chosen: CascadePoint | None
    target_accuracy: float | None


@dataclass(frozen=True, slots=True)
class ErrorCorrelation:
    """Does the strong judge fail on the same items as the cheap judge?"""

    cheap_wrong: Estimate
    strong_wrong: Estimate
    strong_wrong_given_cheap_wrong: Estimate | None

    @property
    def lift(self) -> float | None:
        """``P(strong wrong | cheap wrong) / P(strong wrong)``; about 1 means independent."""
        conditional = self.strong_wrong_given_cheap_wrong
        if conditional is None or self.strong_wrong.point == 0:
            return None
        return conditional.point / self.strong_wrong.point


def _probabilities(name: str, values: npt.ArrayLike) -> npt.NDArray[np.float64]:
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError(f"{name} must be a non-empty 1-D array")
    if not np.all(np.isfinite(arr)) or np.any((arr < 0) | (arr > 1)):
        raise ValueError(f"{name} must contain probabilities in [0, 1] (no NaN)")
    return arr


def cascade_predictions(
    cheap_prob: npt.ArrayLike, strong: npt.ArrayLike, threshold: float
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.bool_]]:
    """Combined 0/1 verdicts and the mask of items the cheap judge decided."""
    p = _probabilities("cheap_prob", cheap_prob)
    s = as_binary("strong", strong)
    check_same_length("cheap_prob", p, "strong", s)
    if not 0.5 <= threshold <= 1.0 + 1e-12:
        raise ValueError(f"threshold must be in [0.5, 1], got {threshold}")
    accept_pass = p >= threshold
    accept_fail = p <= 1 - threshold
    accepted = accept_pass | accept_fail
    combined = np.where(accepted, accept_pass.astype(np.int64), s)
    return combined.astype(np.int64), accepted


def cascade_curve(
    cheap_prob: npt.ArrayLike,
    strong: npt.ArrayLike,
    human: npt.ArrayLike,
    *,
    target_accuracy: float | None = None,
    thresholds: npt.ArrayLike | None = None,
) -> CascadeCurve:
    """Accuracy and coverage at each threshold; choose the cheapest that meets the target.

    The chosen threshold is the one with the **highest coverage** (fewest escalations)
    whose accuracy point estimate is at least ``target_accuracy``. Choose it on dev and
    report it on test: picking a threshold on the same data you report is optimistic.
    """
    p = _probabilities("cheap_prob", cheap_prob)
    s = as_binary("strong", strong)
    h = as_binary("human", human)
    check_same_length("cheap_prob", p, "human", h)
    check_same_length("strong", s, "human", h)
    if target_accuracy is not None and not 0 < target_accuracy <= 1:
        raise ValueError("target_accuracy must be in (0, 1]")
    if thresholds is None:
        confidence = np.maximum(p, 1 - p)
        grid = np.unique(np.concatenate([[0.5], confidence, [1.0]]))
    else:
        grid = np.unique(np.asarray(thresholds, dtype=np.float64))
    n = int(h.size)
    points: list[CascadePoint] = []
    for tau in grid:
        combined, accepted = cascade_predictions(p, s, float(tau))
        correct = int((combined == h).sum())
        points.append(
            CascadePoint(
                threshold=float(tau),
                coverage=float(accepted.mean()),
                accuracy=wilson_interval(correct, n),
                escalations=int(n - accepted.sum()),
            )
        )
    cheap_pred = (p >= 0.5).astype(np.int64)
    chosen = None
    if target_accuracy is not None:
        eligible = [point for point in points if point.accuracy.point >= target_accuracy]
        if eligible:
            chosen = max(eligible, key=lambda point: (point.coverage, -point.threshold))
    return CascadeCurve(
        points=tuple(points),
        cheap_accuracy=wilson_interval(int((cheap_pred == h).sum()), n),
        strong_accuracy=wilson_interval(int((s == h).sum()), n),
        chosen=chosen,
        target_accuracy=target_accuracy,
    )


def error_correlation(
    cheap: npt.ArrayLike, strong: npt.ArrayLike, human: npt.ArrayLike
) -> ErrorCorrelation:
    """``P(strong wrong)`` vs ``P(strong wrong | cheap wrong)``, each with a Wilson interval.

    If the conditional is much higher than the marginal, the judges fail on the same
    items and escalating to the strong judge buys little.
    """
    c = as_binary("cheap", cheap)
    s = as_binary("strong", strong)
    h = as_binary("human", human)
    check_same_length("cheap", c, "human", h)
    check_same_length("strong", s, "human", h)
    cheap_wrong = c != h
    strong_wrong = s != h
    n = int(h.size)
    conditional = None
    if cheap_wrong.any():
        conditional = wilson_interval(
            int((strong_wrong & cheap_wrong).sum()), int(cheap_wrong.sum())
        )
    return ErrorCorrelation(
        cheap_wrong=wilson_interval(int(cheap_wrong.sum()), n),
        strong_wrong=wilson_interval(int(strong_wrong.sum()), n),
        strong_wrong_given_cheap_wrong=conditional,
    )
