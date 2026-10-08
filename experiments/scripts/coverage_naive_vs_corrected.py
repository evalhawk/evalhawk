"""Card #19 S7: Coverage simulation script over a θ grid.

Simulates coverage for naive, Rogan-Gladen, PPI, and clustered methods across
θ ∈ {0.1, 0.2, ..., 0.9}. Plots coverage vs θ with a 95% line and ±1.5-point band.

Usage:
    uv run --group experiments python experiments/scripts/coverage_naive_vs_corrected.py

Optional flags:
    --reps REPS    Number of replicates per setting (default: 2000).
    --seed SEED    Random seed (default: 12345).
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt

from evalhawk.stats.clustered import clustered_mean_interval
from evalhawk.stats.correction import corrected_pass_rate, ppi_mean
from evalhawk.stats.intervals import wilson_interval

KAPPA_INTRACLUSTER = 4  # ICC = 1/(κ+1) = 0.2; design effect = 1+9*ICC = 2.8.
N_CAL = 500
N_TEST = 2000
N_CLUSTERS = 200
CLUSTER_SIZE = 10
N_BOOT = 1000
SENSITIVITY = 0.9
SPECIFICITY = 0.8

BinaryArray = npt.NDArray[np.int64]
METHOD_LABELS = {
    "naive": "Naive Wilson (judge, iid)",
    "rogan_gladen": "Rogan–Gladen (iid)",
    "ppi": "PPI (iid)",
    "clustered_a": "Cluster-robust (human)",
    "clustered_a_naive": "Wilson (human, ignoring clusters)",
    "clustered_b": "Rogan–Gladen (clustered judge)",
    "clustered_b_unclustered": "Rogan–Gladen (ignoring clusters)",
}


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



def _run_coverage_simulation(theta: float, reps: int, seed: int) -> dict[str, float]:
    """Count coverage in iid and clustered worlds using independent, fixed random streams.

    Every clustered comparison uses the same observations. Bootstrap randomness
    cannot change subsequent simulated worlds. Exceptions are not dropped or retried.
    """
    rng = np.random.default_rng(seed)
    rng_clustered = np.random.default_rng(seed + 3000)
    rng_boot = np.random.default_rng(seed + 1000)
    rng_cluster_boot = np.random.default_rng(seed + 4000)
    rng_baseline = np.random.default_rng(seed + 5000)
    covered = dict.fromkeys(METHOD_LABELS, 0)

    for _ in range(reps):
        human_cal, judge_cal, _, judge_test = _simulate_world_iid(
            theta, SENSITIVITY, SPECIFICITY, N_CAL, N_TEST, rng=rng
        )
        estimates = {
            "naive": wilson_interval(int(judge_test.sum()), N_TEST),
            "rogan_gladen": corrected_pass_rate(
                judge_test, judge_cal, human_cal, rng=rng_boot, n_boot=N_BOOT
            ),
            "ppi": ppi_mean(human_cal, judge_cal, judge_test),
        }
        human_cal, judge_cal, human_test, judge_test, clusters = _simulate_world_clustered(
            theta, SENSITIVITY, SPECIFICITY, N_CAL, N_CLUSTERS, CLUSTER_SIZE, rng=rng_clustered
        )
        estimates.update({
            "clustered_a": clustered_mean_interval(human_test, clusters),
            "clustered_a_naive": wilson_interval(int(human_test.sum()), N_TEST),
            "clustered_b": corrected_pass_rate(
                judge_test,
                judge_cal,
                human_cal,
                rng=rng_cluster_boot,
                n_boot=N_BOOT,
                test_clusters=clusters,
            ),
            "clustered_b_unclustered": corrected_pass_rate(
                judge_test, judge_cal, human_cal, rng=rng_baseline, n_boot=N_BOOT
            ),
        })
        for method, estimate in estimates.items():
            covered[method] += int(estimate.low <= theta <= estimate.high)

    return {method: count / reps for method, count in covered.items()}


def main() -> None:
    """Simulate the theta grid and write the coverage chart; never run on import."""
    parser = argparse.ArgumentParser(description="Coverage: naive vs corrected intervals")
    parser.add_argument("--reps", type=int, default=2000, help="Replicates per setting")
    parser.add_argument("--seed", type=int, default=12345, help="Random seed")
    args = parser.parse_args()
    if args.reps < 1:
        parser.error("--reps must be a positive integer")
    if args.seed < 0:
        parser.error("--seed must be a non-negative integer")

    theta_grid = np.linspace(0.1, 0.9, 9)
    results: dict[str, list[float]] = {method: [] for method in METHOD_LABELS}
    for index, theta in enumerate(theta_grid):
        coverage = _run_coverage_simulation(float(theta), args.reps, args.seed + index)
        for method in results:
            results[method].append(coverage[method])

    fig, ax = plt.subplots(figsize=(11, 7))
    ax.axhline(0.95, color="black", linestyle="--", linewidth=1, label="Target (95%)")
    ax.axhspan(0.935, 0.965, alpha=0.15, color="green", label="±1.5-point band")
    for method, label in METHOD_LABELS.items():
        ax.plot(theta_grid, results[method], marker="o", linewidth=1.5, label=label)
    ax.set_xlabel("True pass rate (θ)")
    ax.set_ylabel("Empirical coverage")
    ax.set_title(
        f"Coverage: {args.reps} replicates per setting, seed={args.seed}\n"
        f"s={SENSITIVITY}, c={SPECIFICITY}, n_cal={N_CAL}, N={N_TEST}; "
        f"G={N_CLUSTERS}, cluster size={CLUSTER_SIZE}, κ={KAPPA_INTRACLUSTER}"
    )
    # Include zero: biased naive intervals can miss essentially every world.
    ax.set_ylim(0, 1.02)
    ax.set_xticks(theta_grid)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    output_dir = Path(__file__).resolve().parents[1] / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / "coverage_naive_vs_corrected.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
