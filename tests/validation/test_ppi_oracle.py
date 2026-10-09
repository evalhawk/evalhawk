"""Card #9 S5: PPI oracle validation against ppi_py."""

import pytest

from evalhawk.stats.correction import ppi_mean

ppi_py = pytest.importorskip("ppi_py")


class TestPPIOracle:
    """Compare against ppi_py with lam=1 (classical PPI, not PPI++)."""

    @pytest.mark.slow
    def test_oracle_point_estimate_seed_1(self) -> None:
        """Oracle: seed 1, compare point estimate to ppi_py."""
        import numpy as np

        rng = np.random.default_rng(2024)

        # Labeled set
        Y = rng.uniform(0, 1, size=50)
        Yhat = Y + rng.normal(0, 0.15, size=50)
        Yhat = np.clip(Yhat, 0, 1)

        # Unlabeled set
        Yhat_unlabeled = rng.uniform(0, 1, size=500)

        # Our implementation
        est = ppi_mean(Y, Yhat, Yhat_unlabeled)

        # ppi_py reference (with lam=1 for classical PPI)
        ref_point = ppi_py.ppi_mean_pointestimate(Y, Yhat, Yhat_unlabeled, lam=1)

        assert abs(est.point - ref_point) < 1e-6, (
            f"Point estimate mismatch: {est.point} vs {ref_point}"
        )

    @pytest.mark.slow
    def test_oracle_interval_seed_1(self) -> None:
        """Oracle: seed 1, compare interval to ppi_py."""
        import numpy as np

        rng = np.random.default_rng(2024)

        # Labeled set
        Y = rng.uniform(0, 1, size=50)
        Yhat = Y + rng.normal(0, 0.15, size=50)
        Yhat = np.clip(Yhat, 0, 1)

        # Unlabeled set
        Yhat_unlabeled = rng.uniform(0, 1, size=500)

        # Our implementation (95% confidence)
        est = ppi_mean(Y, Yhat, Yhat_unlabeled, confidence=0.95)

        # ppi_py reference (alpha = 1 - confidence = 0.05, lam=1)
        ref_low, ref_high = ppi_py.ppi_mean_ci(Y, Yhat, Yhat_unlabeled, alpha=1 - 0.95, lam=1)

        assert abs(est.low - ref_low) < 1e-6, f"Lower bound mismatch: {est.low} vs {ref_low}"
        assert abs(est.high - ref_high) < 1e-6, f"Upper bound mismatch: {est.high} vs {ref_high}"

    @pytest.mark.slow
    def test_oracle_point_estimate_seed_2(self) -> None:
        """Oracle: seed 2, compare point estimate to ppi_py."""
        import numpy as np

        rng = np.random.default_rng(2025)

        # Labeled set
        Y = rng.binomial(1, 0.4, size=80)
        Yhat = rng.uniform(0, 1, size=80)

        # Unlabeled set
        Yhat_unlabeled = rng.uniform(0, 1, size=1000)

        # Our implementation
        est = ppi_mean(Y, Yhat, Yhat_unlabeled)

        # ppi_py reference
        ref_point = ppi_py.ppi_mean_pointestimate(Y, Yhat, Yhat_unlabeled, lam=1)

        assert abs(est.point - ref_point) < 1e-6

    @pytest.mark.slow
    def test_oracle_interval_seed_2(self) -> None:
        """Oracle: seed 2, compare interval to ppi_py."""
        import numpy as np

        rng = np.random.default_rng(2025)

        # Labeled set
        Y = rng.binomial(1, 0.4, size=80)
        Yhat = rng.uniform(0, 1, size=80)

        # Unlabeled set
        Yhat_unlabeled = rng.uniform(0, 1, size=1000)

        # Our implementation
        est = ppi_mean(Y, Yhat, Yhat_unlabeled, confidence=0.95)

        # ppi_py reference
        ref_low, ref_high = ppi_py.ppi_mean_ci(Y, Yhat, Yhat_unlabeled, alpha=0.05, lam=1)

        assert abs(est.low - ref_low) < 1e-6
        assert abs(est.high - ref_high) < 1e-6

    @pytest.mark.slow
    def test_oracle_point_estimate_seed_3(self) -> None:
        """Oracle: seed 3, compare point estimate to ppi_py."""
        import numpy as np

        rng = np.random.default_rng(2026)

        # Labeled set: tight correlation
        Y = rng.uniform(0, 1, size=120)
        Yhat = Y + rng.normal(0, 0.05, size=120)
        Yhat = np.clip(Yhat, 0, 1)

        # Unlabeled set
        Yhat_unlabeled = rng.uniform(0, 1, size=800)

        # Our implementation
        est = ppi_mean(Y, Yhat, Yhat_unlabeled)

        # ppi_py reference
        ref_point = ppi_py.ppi_mean_pointestimate(Y, Yhat, Yhat_unlabeled, lam=1)

        assert abs(est.point - ref_point) < 1e-6

    @pytest.mark.slow
    def test_oracle_interval_seed_3(self) -> None:
        """Oracle: seed 3, compare interval to ppi_py."""
        import numpy as np

        rng = np.random.default_rng(2026)

        # Labeled set: tight correlation
        Y = rng.uniform(0, 1, size=120)
        Yhat = Y + rng.normal(0, 0.05, size=120)
        Yhat = np.clip(Yhat, 0, 1)

        # Unlabeled set
        Yhat_unlabeled = rng.uniform(0, 1, size=800)

        # Our implementation
        est = ppi_mean(Y, Yhat, Yhat_unlabeled, confidence=0.95)

        # ppi_py reference
        ref_low, ref_high = ppi_py.ppi_mean_ci(Y, Yhat, Yhat_unlabeled, alpha=0.05, lam=1)

        assert abs(est.low - ref_low) < 1e-6
        assert abs(est.high - ref_high) < 1e-6
