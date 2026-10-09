"""Version comparison: run v1 and v2 on the same inputs and compare outcomes (S4).

McNemar exact test for paired binary data disagreements, paired bootstrap for
estimating the difference, and decision logic based on confidence intervals.
"""

import math
from typing import SupportsIndex

import numpy as np
import numpy.typing as npt

from evalhawk.core.results import Decision, Estimate
from evalhawk.stats._checks import (
    as_binary,
    as_count,
    check_confidence,
    check_n_boot,
    check_same_length,
)
from evalhawk.stats.clustered import cluster_bootstrap_means


def mcnemar_exact(b: SupportsIndex, c: SupportsIndex) -> float:
    """Two-sided exact binomial test for paired data (McNemar 1947).

    Given b = count of (v1=PASS, v2=FAIL) and c = count of (v1=FAIL, v2=PASS),
    test the null hypothesis that v1 and v2 have the same error rate using
    a binomial distribution. Computes the two-sided p-value using log-space
    arithmetic for numerical stability.

    Args:
        b: Count of v1 PASS, v2 FAIL pairs (a non-negative Python or NumPy integer).
        c: Count of v1 FAIL, v2 PASS pairs (a non-negative Python or NumPy integer).

    Returns:
        The two-sided p-value, in [0, 1].

    Raises:
        ValueError: If b or c is negative or a bool, or if not an int.

    References:
        McNemar, Q. (1947). Note on the sampling error of the difference
        between correlated proportions or percentages. Psychometrika, 12(2),
        153-157.

    Examples:
        >>> mcnemar_exact(12, 30)
        0.007918...
        >>> mcnemar_exact(0, 0)
        1.0
        >>> mcnemar_exact(7, 7)
        1.0
    """
    # Validate inputs (Python or NumPy integers are fine; bool and float are not)
    b = as_count("b", b)
    c = as_count("c", c)
    if b < 0:
        raise ValueError(f"b must be >= 0, got {b!r}")
    if c < 0:
        raise ValueError(f"c must be >= 0, got {c!r}")

    n = b + c

    # Early returns
    if n == 0 or b == c:
        return 1.0

    # Compute two-sided p-value using log-space binomial tail
    k = min(b, c)

    # log_t(0) = n * log(0.5) = n * log(2^(-1)) = -n * log(2)
    # But we compute log(binom(n, i)) + log(0.5^n)
    # = log(binom(n, i)) - n * log(2)

    # Store log-space terms
    log_t: list[float] = []

    # i = 0: log(binom(n, 0)) - n*log(2) = 0 - n*log(2) = -n*log(2)
    log_t.append(-n * math.log(2))

    # i = 1..k: log_t(i) = log_t(i-1) + log(n - (i-1)) - log(i)
    for i in range(1, k + 1):
        prev = log_t[-1]
        term = prev + math.log(n - i + 1) - math.log(i)
        log_t.append(term)

    # Log-sum-exp: compute m = max(log_t)
    m = max(log_t)
    # sum = m + log(sum(exp(log_t - m)))
    log_sum = m + math.log(sum(math.exp(x - m) for x in log_t))

    # Two-sided p-value: 2 * P(X <= k | n, p=0.5) if k < n/2, else cumulative
    log_tail = log_sum
    p_one_sided = math.exp(log_tail)
    p_two_sided = min(1.0, 2.0 * p_one_sided)

    return p_two_sided


def decide(diff: Estimate) -> Decision:
    """Decide if v2 is better, worse, or inconclusive vs v1.

    Based on the confidence interval of the difference:
    - If low > 0: v2 is clearly BETTER
    - If high < 0: v2 is clearly WORSE
    - Otherwise (interval includes 0): INCONCLUSIVE

    Args:
        diff: The difference estimate (v2 - v1).

    Returns:
        A Decision: "BETTER", "WORSE", or "INCONCLUSIVE".
    """
    if diff.low > 0:
        return "BETTER"
    if diff.high < 0:
        return "WORSE"
    return "INCONCLUSIVE"


def paired_bootstrap(
    a: npt.ArrayLike,
    b: npt.ArrayLike,
    *,
    rng: np.random.Generator,
    n_boot: int = 2000,
    confidence: float = 0.95,
    clusters: npt.ArrayLike | None = None,
) -> Estimate:
    """Bootstrap confidence interval for difference of paired binary outcomes.

    Given paired binary arrays a (v1) and b (v2), computes the point estimate
    and confidence interval for the mean difference d = b - a. Uses example-index
    resampling (not count-based) with chunking to bound memory usage.

    When clusters is provided, resamples cluster indices instead of individual
    examples, accounting for within-cluster correlation (e.g., multiple items
    from the same document).

    Args:
        a: Binary outcomes from v1 (0/1). Must be array-like, 1-D, non-empty.
        b: Binary outcomes from v2 (0/1). Must be array-like, same length as a.
        rng: NumPy random generator for reproducibility.
        n_boot: Number of bootstrap resamples. Must be >= 100. Defaults to 2000.
        confidence: Confidence level for interval, in (0, 1). Defaults to 0.95.
        clusters: Optional cluster labels (any 1-D labels). When provided,
            resamples cluster indices instead of individual examples.
            Must have >= 2 unique clusters. Defaults to None (independent resampling).

    Returns:
        An Estimate with:
        - point: mean(b - a) on observed data
        - low, high: percentile interval at (1-confidence)/2 and (1+confidence)/2
        - n: number of pairs
        - method: "paired_bootstrap" (or "paired_cluster_bootstrap" if clusters given)
        - confidence: as specified

    Raises:
        ValueError: If a and b have different lengths, n_boot < 100, or
            confidence not in (0, 1). If clusters is given, also raises if
            clusters and a have different lengths or if there is only one cluster.

    References:
        Efron, B., & Tibshirani, R. J. (1993). An introduction to the bootstrap.
        Chapman and Hall/CRC.

    Examples:
        >>> a = np.array([0, 1, 0, 1])
        >>> b = np.array([0, 1, 1, 1])
        >>> rng = np.random.default_rng(42)
        >>> est = paired_bootstrap(a, b, rng=rng, n_boot=100)
        >>> est.point
        0.25
    """
    # Convert to arrays (binary-validated)
    a_arr = as_binary("a", a)
    b_arr = as_binary("b", b)

    # Validate lengths
    check_same_length("a", a_arr, "b", b_arr)

    # Validate n_boot and confidence
    check_n_boot(n_boot)
    check_confidence(confidence)

    n = len(a_arr)

    # Compute differences
    d = b_arr - a_arr  # shape (n,), values in {-1, 0, +1}

    # Point estimate
    point = float(np.mean(d))

    # If no clusters, use standard index resampling
    if clusters is None:
        # Bootstrap resampling with chunking
        chunk_size = 100
        bootstrap_diffs: list[float] = []

        for chunk_start in range(0, n_boot, chunk_size):
            chunk_end = min(chunk_start + chunk_size, n_boot)
            chunk_n = chunk_end - chunk_start

            # Resample indices: (chunk_n, n)
            idx = rng.integers(0, n, size=(chunk_n, n))

            # Compute bootstrap differences: (chunk_n,)
            diff_chunk = d[idx].mean(axis=1)
            bootstrap_diffs.extend(diff_chunk.tolist())

        bootstrap_diffs_arr = np.array(bootstrap_diffs)
        method = "paired_bootstrap"
    else:
        # Cluster-aware resampling
        c_arr = np.asarray(clusters)
        check_same_length("a", a_arr, "clusters", c_arr)
        bootstrap_diffs_arr = cluster_bootstrap_means(d, c_arr, rng=rng, n_boot=n_boot)
        method = "paired_cluster_bootstrap"

    # Compute percentile interval
    lower_q = (1 - confidence) / 2
    upper_q = (1 + confidence) / 2
    low, high = np.quantile(bootstrap_diffs_arr, [lower_q, upper_q])

    return Estimate(
        point=point,
        low=float(low),
        high=float(high),
        n=n,
        method=method,
        confidence=confidence,
    )
