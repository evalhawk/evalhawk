"""Coverage simulation for the bias-corrected paired comparison (slow).

A synthetic judge with known sensitivity and specificity grades two versions whose true
pass rates differ by a known amount. Over many simulated studies, the 95% interval of
the corrected difference must contain the true difference about 95% of the time, while
the uncorrected judged difference is biased towards zero.
"""

import numpy as np
import pytest

from evalhawk.stats.paired_correction import corrected_paired_difference

pytestmark = pytest.mark.slow


def _study(rng: np.random.Generator, *, s: float, c: float, theta_a: float, delta: float):
    n_test, n_cal = 600, 300
    truth_a = rng.random(n_test) < theta_a
    # candidate fixes some baseline failures (paired, correlated outcomes)
    fix_prob = delta / (1 - theta_a)
    truth_b = truth_a | (rng.random(n_test) < fix_prob)

    def judge(truth: np.ndarray) -> np.ndarray:
        u = rng.random(truth.size)
        return np.where(truth, u < s, u > c).astype(int)

    human_cal = rng.random(n_cal) < 0.6
    return (
        judge(truth_a),
        judge(truth_b),
        judge(human_cal),
        human_cal.astype(int),
        float(truth_b.mean() - truth_a.mean()),
    )


@pytest.mark.parametrize(("s", "c"), [(0.9, 0.85), (0.85, 0.6)])
def test_corrected_interval_covers_the_true_difference(s: float, c: float) -> None:
    rng = np.random.default_rng(20261101)
    runs, covered, naive_bias = 400, 0, []
    for _ in range(runs):
        a, b, judge_cal, human_cal, true_delta = _study(rng, s=s, c=c, theta_a=0.6, delta=0.08)
        estimate = corrected_paired_difference(a, b, judge_cal, human_cal, rng=rng, n_boot=500)
        covered += estimate.low <= true_delta <= estimate.high
        naive_bias.append((b - a).mean() - true_delta)
    coverage = covered / runs
    assert 0.92 <= coverage <= 0.98, f"coverage {coverage:.3f}"
    # the uncorrected judged difference is shrunk towards zero by J = s + c - 1
    assert np.mean(naive_bias) < -0.005
