import numpy as np
import pytest

from evalhawk.core.errors import JudgeTooWeakError
from evalhawk.stats.paired_correction import corrected_paired_difference

RNG = np.random.default_rng(0)


def _calibration(s: float, c: float, n: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """Exact calibration counts for sensitivity s and specificity c."""
    passes, fails = n // 2, n - n // 2
    human = np.array([1] * passes + [0] * fails)
    judge = np.array(
        [1] * round(s * passes)
        + [0] * (passes - round(s * passes))
        + [0] * round(c * fails)
        + [1] * (fails - round(c * fails))
    )
    return judge, human


def test_point_is_judged_difference_divided_by_youden_j() -> None:
    baseline = np.array([0] * 60 + [1] * 40)
    candidate = np.array([0] * 50 + [1] * 50)  # judged difference = +0.10
    judge, human = _calibration(0.8, 0.7)  # J = 0.5
    result = corrected_paired_difference(baseline, candidate, judge, human, rng=RNG)
    assert result.point == pytest.approx(0.10 / 0.5)
    assert result.low <= result.point <= result.high
    assert result.method == "paired_rogan_gladen+bootstrap"


def test_a_perfect_judge_changes_nothing() -> None:
    baseline = np.array([0, 1, 1, 0, 1, 0, 1, 1])
    candidate = np.array([1, 1, 1, 0, 1, 1, 1, 1])
    judge, human = _calibration(1.0, 1.0)
    result = corrected_paired_difference(baseline, candidate, judge, human, rng=RNG)
    assert result.point == pytest.approx((candidate - baseline).mean())


def test_weak_judges_and_one_sided_calibration_are_refused() -> None:
    pairs = np.array([0, 1] * 10), np.array([1, 1] * 10)
    weak = _calibration(0.55, 0.52)
    with pytest.raises(JudgeTooWeakError, match="too weak"):
        corrected_paired_difference(*pairs, *weak, rng=RNG)
    with pytest.raises(ValueError, match="both PASS and FAIL"):
        corrected_paired_difference(*pairs, np.ones(10, dtype=int), np.ones(10, dtype=int), rng=RNG)


def test_clusters_widen_the_interval() -> None:
    rng = np.random.default_rng(1)
    groups = np.repeat(np.arange(50), 4)  # 50 cases x 4 near-identical paraphrases
    case_effect = rng.random(50) < 0.5
    baseline = np.repeat(case_effect, 4).astype(int)
    candidate = np.repeat(case_effect | (rng.random(50) < 0.3), 4).astype(int)
    judge, human = _calibration(0.9, 0.85)
    iid = corrected_paired_difference(
        baseline, candidate, judge, human, rng=np.random.default_rng(2)
    )
    clustered = corrected_paired_difference(
        baseline, candidate, judge, human, rng=np.random.default_rng(2), clusters=groups
    )
    assert clustered.point == pytest.approx(iid.point)
    assert (clustered.high - clustered.low) > (iid.high - iid.low)
