"""Cluster-robust standard errors and bootstrap (card S6).

When multiple observations come from the same cluster (e.g., ten questions about
the same document), treating them as independent underestimates error. This module
provides cluster-robust standard errors and cluster-aware bootstrap resampling.

References:
    - Liang, K.-Y., & Zeger, S. L. (1986). "Longitudinal data analysis using
      generalized linear models." Biometrika, 73(1), 13–22.
"""

import math

import numpy as np
import numpy.typing as npt

from evalhawk.core.results import Estimate
from evalhawk.stats._checks import check_confidence, check_same_length, z_value


def cluster_robust_se(scores: npt.ArrayLike, clusters: npt.ArrayLike) -> float:
    """Cluster-robust standard error using Liang-Zeger method.

    Accounts for within-cluster correlation by computing the variance of
    cluster-level sums. Formula:
        x̄ = mean(scores)
        Var = (1/n²) · Σ_g (Σ_{i∈g} (s_i − x̄))²
        SE = √Var

    Note: No small-sample G/(G−1) factor is applied. Therefore, singleton
    clusters (one item per cluster) yield SE = std(scores, ddof=0) / √n,
    which equals the ordinary SE.

    Args:
        scores: Array of numerical values. Must be 1-D, numeric, non-empty.
        clusters: Array of cluster labels (any 1-D labels, including strings).
            Converted internally using np.unique(..., return_inverse=True).

    Returns:
        The cluster-robust standard error as a float.

    Raises:
        ValueError: If scores and clusters have different lengths, if n < 2,
            or if there is only one cluster.

    References:
        - Liang, K.-Y., & Zeger, S. L. (1986). "Longitudinal data analysis
          using generalized linear models." Biometrika, 73(1), 13–22.
    """
    # Convert to arrays
    s_arr = np.asarray(scores, dtype=np.float64)
    c_arr = np.asarray(clusters)

    # Validate lengths
    check_same_length("scores", s_arr, "clusters", c_arr)

    n = len(s_arr)

    # Validate n >= 2
    if n < 2:
        raise ValueError(f"n must be >= 2, got {n!r}")

    # Get unique clusters and map to indices
    unique_clusters, cluster_indices = np.unique(c_arr, return_inverse=True)
    n_clusters = len(unique_clusters)

    # Validate at least 2 clusters
    if n_clusters < 2:
        raise ValueError(f"clusters must have at least 2 unique values, got {n_clusters!r}")

    # Compute mean
    x_bar = float(np.mean(s_arr))

    # Compute cluster sums: Σ_{i∈g} (s_i − x̄)
    cluster_sums = np.bincount(cluster_indices.ravel(), weights=s_arr - x_bar, minlength=n_clusters)

    # Compute variance: (1/n²) · Σ_g cluster_sums[g]²
    var = float(np.sum(cluster_sums**2)) / (n**2)

    return math.sqrt(var)


def cluster_bootstrap_means(
    values: npt.ArrayLike,
    clusters: npt.ArrayLike,
    *,
    rng: np.random.Generator,
    n_boot: int,
) -> npt.NDArray[np.float64]:
    """Bootstrap means of ``values``, resampling whole clusters with replacement.

    Each resample draws as many clusters as there are in the data; its mean is the
    sum of the drawn clusters' values divided by the number of items in them.

    Args:
        values: Numerical values, one per item.
        clusters: Cluster label per item (any 1-D labels). Needs >= 2 distinct clusters.
        rng: NumPy random generator for resampling.
        n_boot: Number of bootstrap resamples.

    Returns:
        Array of ``n_boot`` resampled means.

    Raises:
        ValueError: If lengths differ or there is only one cluster.
    """
    v_arr = np.asarray(values, dtype=np.float64)
    c_arr = np.asarray(clusters)
    check_same_length("values", v_arr, "clusters", c_arr)

    _, inverse = np.unique(c_arr, return_inverse=True)
    inverse = inverse.ravel()
    n_clusters = int(inverse.max()) + 1
    if n_clusters < 2:
        raise ValueError(
            f"clusters must have at least 2 unique values for bootstrap, got {n_clusters!r}"
        )

    sums = np.bincount(inverse, weights=v_arr, minlength=n_clusters)
    sizes = np.bincount(inverse, minlength=n_clusters).astype(np.float64)

    means = np.empty(n_boot, dtype=np.float64)
    chunk = 100  # bounds memory at chunk * n_clusters draws
    for start in range(0, n_boot, chunk):
        stop = min(start + chunk, n_boot)
        draws = rng.integers(0, n_clusters, size=(stop - start, n_clusters))
        means[start:stop] = sums[draws].sum(axis=1) / sizes[draws].sum(axis=1)
    return means


def clustered_mean_interval(
    scores: npt.ArrayLike,
    clusters: npt.ArrayLike,
    *,
    confidence: float = 0.95,
) -> Estimate:
    """Confidence interval for the mean using cluster-robust SE.

    Computes x̄ ± z·cluster_robust_se, where z is the critical value for
    the given confidence level.

    Args:
        scores: Array of numerical values. Must be 1-D, numeric, non-empty.
        clusters: Array of cluster labels (any 1-D labels, including strings).
        confidence: Confidence level (e.g., 0.95 for 95%). Must be in (0, 1).
            Defaults to 0.95.

    Returns:
        An Estimate with point=mean(scores), bounds via cluster_robust_se,
        method="cluster_robust", n=len(scores), and the given confidence.

    Raises:
        ValueError: If scores and clusters have different lengths, if n < 2,
            if there is only one cluster, or if confidence not in (0, 1).

    References:
        - Liang, K.-Y., & Zeger, S. L. (1986). "Longitudinal data analysis
          using generalized linear models." Biometrika, 73(1), 13–22.
    """
    # Validate confidence
    check_confidence(confidence)

    # Convert to arrays
    s_arr = np.asarray(scores, dtype=np.float64)
    c_arr = np.asarray(clusters)

    # Validate lengths
    check_same_length("scores", s_arr, "clusters", c_arr)

    n = len(s_arr)

    # Validate n >= 2 and at least 2 clusters (delegated to cluster_robust_se)
    # Compute cluster-robust SE (will raise if validation fails)
    se = cluster_robust_se(s_arr, c_arr)

    # Compute mean
    point = float(np.mean(s_arr))

    # Compute z-score
    z = z_value(confidence)

    # Compute bounds
    low = point - z * se
    high = point + z * se

    return Estimate(
        point=point,
        low=low,
        high=high,
        n=n,
        method="cluster_robust",
        confidence=confidence,
    )
