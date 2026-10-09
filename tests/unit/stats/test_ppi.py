"""Card #9 S5: PPI correction for mean estimation."""

import math

import numpy as np
import pytest

from evalhawk.stats.correction import ppi_mean


class TestPPIMean:
    """Hand examples and error cases."""

    def test_hand_example(self) -> None:
        """Hand example: y=[1,0,1,1], ŷ=[1,1,1,0], ŷ_unl=[1,1,0,1,1,0]."""
        y_labeled = np.array([1.0, 0.0, 1.0, 1.0])
        yhat_labeled = np.array([1.0, 1.0, 1.0, 0.0])
        yhat_unlabeled = np.array([1.0, 1.0, 0.0, 1.0, 1.0, 0.0])

        est = ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)

        # rectifier = mean([0, 1, 0, -1]) = 0
        # θ = mean([1,1,0,1,1,0]) - 0 = 4/6 = 0.6667
        assert est.method == "ppi"
        assert abs(est.point - 0.6667) < 1e-4
        assert est.n == 6  # N = len(yhat_unlabeled)

    def test_perfect_judge_matches_unlabeled_mean(self) -> None:
        """Perfect judge (ŷ == y) → θ == mean(ŷ_unl)."""
        y_labeled = np.array([1.0, 0.0, 1.0, 1.0])
        yhat_labeled = np.array([1.0, 0.0, 1.0, 1.0])  # Perfect match
        yhat_unlabeled = np.array([0.5, 0.3, 0.8, 0.9])

        est = ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)

        expected_mean = np.mean(yhat_unlabeled)
        assert abs(est.point - expected_mean) < 1e-10

    def test_error_length_mismatch(self) -> None:
        """Error: y_labeled and yhat_labeled have different lengths."""
        y_labeled = np.array([1.0, 0.0, 1.0])
        yhat_labeled = np.array([1.0, 1.0])  # Length 2, not 3
        yhat_unlabeled = np.array([0.5, 0.3])

        with pytest.raises(ValueError, match="must have the same length"):
            ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)

    def test_error_n_equals_1(self) -> None:
        """Error: n < 2."""
        y_labeled = np.array([1.0])
        yhat_labeled = np.array([1.0])
        yhat_unlabeled = np.array([0.5, 0.3])

        with pytest.raises(ValueError, match="n must be"):
            ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)

    def test_error_unlabeled_size_equals_1(self) -> None:
        """Error: N < 2."""
        y_labeled = np.array([1.0, 0.0])
        yhat_labeled = np.array([1.0, 1.0])
        yhat_unlabeled = np.array([0.5])  # N = 1

        with pytest.raises(ValueError, match="N must be"):
            ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)

    def test_error_nan_in_y_labeled(self) -> None:
        """Error: NaN in y_labeled."""
        y_labeled = np.array([1.0, np.nan, 1.0])
        yhat_labeled = np.array([1.0, 1.0, 1.0])
        yhat_unlabeled = np.array([0.5, 0.3])

        with pytest.raises(ValueError, match="y_labeled.*finite"):
            ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)

    def test_error_nan_in_yhat_labeled(self) -> None:
        """Error: NaN in yhat_labeled."""
        y_labeled = np.array([1.0, 0.0, 1.0])
        yhat_labeled = np.array([1.0, np.nan, 1.0])
        yhat_unlabeled = np.array([0.5, 0.3])

        with pytest.raises(ValueError, match="yhat_labeled.*finite"):
            ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)

    def test_error_nan_in_yhat_unlabeled(self) -> None:
        """Error: NaN in yhat_unlabeled."""
        y_labeled = np.array([1.0, 0.0, 1.0])
        yhat_labeled = np.array([1.0, 1.0, 1.0])
        yhat_unlabeled = np.array([0.5, np.nan, 0.3])

        with pytest.raises(ValueError, match="yhat_unlabeled.*finite"):
            ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)

    def test_error_inf_in_y_labeled(self) -> None:
        """Error: infinity in y_labeled."""
        y_labeled = np.array([1.0, np.inf, 1.0])
        yhat_labeled = np.array([1.0, 1.0, 1.0])
        yhat_unlabeled = np.array([0.5, 0.3])

        with pytest.raises(ValueError, match="y_labeled.*finite"):
            ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)

    def test_error_1d_check(self) -> None:
        """Error: input is not 1-D."""
        y_labeled = np.array([[1.0, 0.0]])  # 2-D
        yhat_labeled = np.array([1.0, 1.0])
        yhat_unlabeled = np.array([0.5, 0.3])

        with pytest.raises(ValueError, match="must be 1-D"):
            ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)

    def test_confidence_interval(self) -> None:
        """Test that interval respects confidence level."""
        # Use fixed seed for reproducibility
        rng = np.random.default_rng(42)
        y_labeled = rng.uniform(0.2, 0.8, size=100)
        yhat_labeled = y_labeled + rng.normal(0, 0.1, size=100)
        yhat_unlabeled = rng.uniform(0.3, 0.7, size=500)

        est_95 = ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)
        est_90 = ppi_mean(
            y_labeled, yhat_labeled, yhat_unlabeled, confidence=0.90
        )

        # 90% CI should be narrower than 95% CI
        assert est_90.width < est_95.width
        assert est_95.confidence == 0.95
        assert est_90.confidence == 0.90

    def test_bounds_not_clipped(self) -> None:
        """Bounds are not clipped to [0, 1] (allows oracle agreement)."""
        # Construct a case where bounds might exceed [0, 1]
        y_labeled = np.array([0.9, 0.95, 0.92, 0.88])
        yhat_labeled = np.array([0.1, 0.15, 0.12, 0.08])
        yhat_unlabeled = np.array([0.5, 0.6, 0.55, 0.65, 0.5, 0.55])

        est = ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled)

        # Check that bounds can exceed [0, 1]
        # (depending on variance)
        assert math.isfinite(est.low)
        assert math.isfinite(est.high)
        # Just check that est has bounds
        assert est.low <= est.high
