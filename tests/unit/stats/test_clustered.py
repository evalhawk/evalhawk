"""Tests for clustered error calculations (card S6).

Tests for cluster-robust standard error, clustered bootstrap, and clustered mean interval.
"""

import numpy as np
import pytest

from evalhawk.core.results import Estimate
from evalhawk.stats.clustered import (
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
        
        with pytest.raises(ValueError):
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
        
        with pytest.raises(ValueError):
            clustered_mean_interval(s, clusters)

    def test_confidence_parameter(self) -> None:
        """confidence parameter works."""
        s = np.array([1.0, 2.0, 3.0, 4.0])
        clusters = np.array([0, 0, 1, 1])
        
        est_95 = clustered_mean_interval(s, clusters, confidence=0.95)
        est_90 = clustered_mean_interval(s, clusters, confidence=0.90)
        
        # 90% CI should be narrower than 95% CI
        assert est_90.width < est_95.width
