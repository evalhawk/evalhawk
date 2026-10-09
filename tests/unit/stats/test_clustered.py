"""Tests for clustered error calculations (card S6).

Tests for cluster-robust standard error, clustered bootstrap, and clustered mean interval.
"""

import numpy as np
import pytest

from evalhawk.stats.clustered import (
    cluster_bootstrap_means,
    cluster_robust_se,
    clustered_mean_interval,
)
from evalhawk.stats.compare import paired_bootstrap


# ================================================= cluster_robust_se
class TestClusterRobustSE:
    """Tests for cluster_robust_se function."""

    def test_singleton_clusters_equals_naive_se(self) -> None:
        """Singleton clusters equal naive SE."""
        s = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        n = len(s)
        clusters = np.arange(n)

        result = cluster_robust_se(s, clusters)
        expected = np.std(s, ddof=0) / np.sqrt(n)
        assert result == pytest.approx(expected, rel=1e-10)

    def test_duplicate_items_widen_se(self) -> None:
        """Duplicate items cluster→SE larger than naive SE."""
        s_duplicated = np.array([1.0, 1.0, 1.0, 2.0, 2.0, 2.0])
        clusters_duplicated = np.array([0, 0, 0, 1, 1, 1])

        naive_se = np.std(s_duplicated, ddof=0) / np.sqrt(6)
        clustered_se = cluster_robust_se(s_duplicated, clusters_duplicated)

        assert clustered_se > naive_se

    def test_length_mismatch_raises(self) -> None:
        """Length mismatch raises ValueError."""
        s = np.array([1.0, 2.0, 3.0])
        clusters = np.array([0, 0])

        with pytest.raises(ValueError, match="length"):
            cluster_robust_se(s, clusters)

    def test_n_less_than_2_raises(self) -> None:
        """n < 2 raises ValueError."""
        s = np.array([1.0])
        clusters = np.array([0])

        with pytest.raises(ValueError, match="n"):
            cluster_robust_se(s, clusters)

    def test_single_cluster_raises(self) -> None:
        """Single cluster raises ValueError."""
        s = np.array([1.0, 2.0, 3.0])
        clusters = np.array([0, 0, 0])

        with pytest.raises(ValueError, match="at least 2"):
            cluster_robust_se(s, clusters)

    def test_returns_float(self) -> None:
        """Returns a float."""
        s = np.array([1.0, 2.0, 3.0])
        clusters = np.array([0, 0, 1])

        result = cluster_robust_se(s, clusters)
        assert isinstance(result, float)


# ========================================== clustered_mean_interval
class TestClusteredMeanInterval:
    """Tests for clustered_mean_interval function."""

    def test_returns_cluster_robust_method(self) -> None:
        """Returns method='cluster_robust'."""
        s = np.array([1.0, 2.0, 3.0, 4.0])
        clusters = np.array([0, 0, 1, 1])

        est = clustered_mean_interval(s, clusters)
        assert est.method == "cluster_robust"

    def test_contains_mean(self) -> None:
        """Interval contains the sample mean."""
        s = np.array([1.0, 2.0, 3.0, 4.0])
        clusters = np.array([0, 0, 1, 1])

        est = clustered_mean_interval(s, clusters)
        mean = float(np.mean(s))

        assert est.low <= mean <= est.high

    def test_n_equals_length(self) -> None:
        """n = len(scores)."""
        s = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        clusters = np.array([0, 0, 1, 1, 2])

        est = clustered_mean_interval(s, clusters)
        assert est.n == len(s)

    def test_length_mismatch_raises(self) -> None:
        """Length mismatch raises ValueError."""
        s = np.array([1.0, 2.0, 3.0])
        clusters = np.array([0, 0])

        with pytest.raises(ValueError, match="length"):
            clustered_mean_interval(s, clusters)

    def test_single_cluster_raises(self) -> None:
        """Single cluster raises ValueError."""
        s = np.array([1.0, 2.0, 3.0])
        clusters = np.array([0, 0, 0])

        with pytest.raises(ValueError, match="at least 2"):
            clustered_mean_interval(s, clusters)

    def test_confidence_parameter(self) -> None:
        """confidence parameter works."""
        s = np.array([1.0, 2.0, 3.0, 4.0])
        clusters = np.array([0, 0, 1, 1])

        est_95 = clustered_mean_interval(s, clusters, confidence=0.95)
        est_90 = clustered_mean_interval(s, clusters, confidence=0.90)

        # 90% CI should be narrower than 95% CI
        assert est_90.width < est_95.width


# ========================================== cluster bootstrap
class TestClusterBootstrap:
    """Tests for cluster_bootstrap_means and the clustered paired bootstrap."""

    def test_means_shape_and_reproducible(self) -> None:
        """Returns n_boot means, identical for the same seed."""
        values = np.array([1.0, 0.0, 1.0, 1.0, 0.0, 0.0])
        clusters = np.array([0, 0, 1, 1, 2, 2])

        first = cluster_bootstrap_means(values, clusters, rng=np.random.default_rng(7), n_boot=250)
        second = cluster_bootstrap_means(values, clusters, rng=np.random.default_rng(7), n_boot=250)

        assert first.shape == (250,)
        assert np.array_equal(first, second)

    def test_single_cluster_raises(self) -> None:
        """A single cluster cannot be resampled."""
        with pytest.raises(ValueError, match="at least 2"):
            cluster_bootstrap_means([1.0, 0.0], [0, 0], rng=np.random.default_rng(1), n_boot=100)

    def test_length_mismatch_raises(self) -> None:
        """Length mismatch raises ValueError."""
        with pytest.raises(ValueError, match="same length"):
            cluster_bootstrap_means(
                [1.0, 0.0, 1.0], [0, 1], rng=np.random.default_rng(1), n_boot=100
            )

    def test_paired_cluster_bootstrap_method_name(self) -> None:
        """paired_bootstrap with clusters reports the clustered method."""
        a = [0, 1, 0, 1, 0, 1, 0, 1]
        b = [1, 1, 0, 1, 1, 1, 0, 0]
        clusters = [0, 0, 1, 1, 2, 2, 3, 3]

        est = paired_bootstrap(a, b, rng=np.random.default_rng(3), clusters=clusters)

        assert est.method == "paired_cluster_bootstrap"
        assert est.n == 8

    def test_singleton_clusters_match_unclustered_width(self) -> None:
        """With one item per cluster the interval is about as wide as the iid one."""
        rng_data = np.random.default_rng(11)
        a = rng_data.binomial(1, 0.5, size=2000)
        b = rng_data.binomial(1, 0.55, size=2000)

        iid = paired_bootstrap(a, b, rng=np.random.default_rng(5))
        clustered = paired_bootstrap(a, b, rng=np.random.default_rng(5), clusters=np.arange(2000))

        assert clustered.width == pytest.approx(iid.width, rel=0.1)

    def test_paired_cluster_bootstrap_single_cluster_raises(self) -> None:
        """A single cluster raises ValueError."""
        with pytest.raises(ValueError, match="at least 2"):
            paired_bootstrap([0, 1], [1, 1], rng=np.random.default_rng(1), clusters=[0, 0])
