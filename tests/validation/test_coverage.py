"""Card #19 S7: fixed-seed coverage simulations for known population pass rates.

A 95% interval promises that 95% of intervals built this way contain the truth.
Simulate independent worlds with known truth and count intervals containing it.
Percentile-bootstrap failures must be recorded, not hidden by widening the bands.
"""

from typing import Literal

import numpy as np
import numpy.typing as npt
import pytest

from evalhawk.stats.clustered import clustered_mean_interval
from evalhawk.stats.correction import corrected_pass_rate, ppi_mean
from evalhawk.stats.intervals import wilson_interval

# ================================================================ settings
KAPPA_INTRACLUSTER = 4  # ICC = 1/(κ+1) = 0.2; design effect = 1+9*ICC = 2.8.
N_CAL = 500
N_TEST = 2000
N_CLUSTERS = 200
CLUSTER_SIZE = 10
REPLICATES = 2000
N_BOOT = 1000
SENSITIVITY = 0.9
SPECIFICITY = 0.8

BinaryArray = npt.NDArray[np.int64]
Method = Literal["naive", "rogan_gladen", "ppi", "clustered_a", "clustered_b"]


# ================================================================ simulation helpers
def _judge_verdicts(
    human: BinaryArray, s: float, c: float, *, rng: np.random.Generator
) -> BinaryArray:
    """Draw independent judge flips conditional on human truth, without item loops."""
    return np.asarray(rng.binomial(1, np.where(human == 1, s, 1 - c)), dtype=np.int64)


def _simulate_world_iid(
    theta: float,
    s: float,
    c: float,
    n_cal: int,
    n_test: int,
    *,
    rng: np.random.Generator,
) -> tuple[BinaryArray, BinaryArray, BinaryArray, BinaryArray]:
    """Return human/judge calibration and test labels from independent Bernoulli worlds."""
    human_cal = np.asarray(rng.binomial(1, theta, n_cal), dtype=np.int64)
    human_test = np.asarray(rng.binomial(1, theta, n_test), dtype=np.int64)
    judge_cal = _judge_verdicts(human_cal, s, c, rng=rng)
    judge_test = _judge_verdicts(human_test, s, c, rng=rng)
    return human_cal, judge_cal, human_test, judge_test


def _simulate_world_clustered(
    theta: float,
    s: float,
    c: float,
    n_cal: int,
    n_test_clusters: int,
    n_test_per_cluster: int,
    *,
    rng: np.random.Generator,
) -> tuple[BinaryArray, BinaryArray, BinaryArray, BinaryArray, BinaryArray]:
    """Return iid calibration and beta-Bernoulli test clusters with conditional judge flips."""
    human_cal = np.asarray(rng.binomial(1, theta, n_cal), dtype=np.int64)
    judge_cal = _judge_verdicts(human_cal, s, c, rng=rng)
    cluster_rates = rng.beta(
        theta * KAPPA_INTRACLUSTER, (1 - theta) * KAPPA_INTRACLUSTER, n_test_clusters
    )
    # Broadcasting generates all clusters at once: one shared rate per ten test items.
    human_test = np.asarray(
        rng.binomial(1, cluster_rates[:, None], size=(n_test_clusters, n_test_per_cluster)),
        dtype=np.int64,
    ).ravel()
    judge_test = _judge_verdicts(human_test, s, c, rng=rng)
    test_clusters = np.repeat(np.arange(n_test_clusters, dtype=np.int64), n_test_per_cluster)
    return human_cal, judge_cal, human_test, judge_test, test_clusters


# ================================================================ coverage tests
@pytest.mark.slow
@pytest.mark.parametrize(
    "method",
    ["naive", "rogan_gladen", "ppi", "clustered_a", "clustered_b"],
    ids=["naive", "rogan-gladen", "ppi", "clustered-human", "clustered-rogan-gladen"],
)
@pytest.mark.parametrize(
    ("theta", "seed"), [(0.5, 12345), (0.8, 12346)], ids=["theta=0.5", "theta=0.8"]
)
def test_intervals_cover_known_truth_at_expected_rate(
    method: Method, theta: float, seed: int
) -> None:
    """Corrected intervals cover 93.5–96.5%; iid baselines under-cover clustered truth."""
    # Separate fixed streams keep generated worlds independent of bootstrap consumption.
    rng = np.random.default_rng(seed)
    rng_boot = np.random.default_rng(seed + 1000)
    rng_baseline = np.random.default_rng(seed + 2000)
    covered = 0
    baseline_covered = 0
    clustered = method in ("clustered_a", "clustered_b")

    for _ in range(REPLICATES):
        if clustered:
            human_cal, judge_cal, human_test, judge_test, clusters = _simulate_world_clustered(
                theta, SENSITIVITY, SPECIFICITY, N_CAL, N_CLUSTERS, CLUSTER_SIZE, rng=rng
            )
        else:
            human_cal, judge_cal, human_test, judge_test = _simulate_world_iid(
                theta, SENSITIVITY, SPECIFICITY, N_CAL, N_TEST, rng=rng
            )
            clusters = np.empty(0, dtype=np.int64)

        if method == "naive":
            estimate = wilson_interval(int(judge_test.sum()), N_TEST)
        elif method == "rogan_gladen":
            estimate = corrected_pass_rate(
                judge_test, judge_cal, human_cal, rng=rng_boot, n_boot=N_BOOT
            )
        elif method == "ppi":
            estimate = ppi_mean(human_cal, judge_cal, judge_test)
        elif method == "clustered_a":
            estimate = clustered_mean_interval(human_test, clusters)
            baseline = wilson_interval(int(human_test.sum()), N_TEST)
            baseline_covered += int(baseline.low <= theta <= baseline.high)
        else:
            estimate = corrected_pass_rate(
                judge_test,
                judge_cal,
                human_cal,
                rng=rng_boot,
                n_boot=N_BOOT,
                test_clusters=clusters,
            )
            # Compare intervals on the very same clustered test data and iid calibration.
            baseline = corrected_pass_rate(
                judge_test, judge_cal, human_cal, rng=rng_baseline, n_boot=N_BOOT
            )
            baseline_covered += int(baseline.low <= theta <= baseline.high)
        covered += int(estimate.low <= theta <= estimate.high)

    coverage = covered / REPLICATES
    message = f"{method}, theta={theta}: coverage={coverage:.4f} ({covered}/{REPLICATES})"
    if method == "naive":
        assert coverage < 0.80, message
    else:
        assert 0.935 <= coverage <= 0.965, message
    if clustered:
        baseline_coverage = baseline_covered / REPLICATES
        # Calibration uncertainty is iid and dilutes the cluster effect for Rogan-Gladen,
        # so there the unclustered interval only has to be clearly worse, not below 90%.
        limit = 0.90 if method == "clustered_a" else coverage - 0.02
        assert baseline_coverage < limit, (
            f"{method}, theta={theta}: unclustered coverage={baseline_coverage:.4f}"
        )
