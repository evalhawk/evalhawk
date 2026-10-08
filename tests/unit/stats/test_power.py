"""Tests for power analysis (card S6).

Tests for required_n_paired function.
"""

import pytest

from evalhawk.stats.power import required_n_paired


# ================================================= required_n_paired
class TestRequiredNPaired:
    """Tests for required_n_paired function."""

    def test_known_value_0_2_0_05(self) -> None:
        """required_n_paired(0.2, 0.05) == 621."""
        result = required_n_paired(0.2, 0.05)
        assert result == 621

    def test_larger_delta_smaller_n(self) -> None:
        """Larger delta → smaller n."""
        n_small_delta = required_n_paired(0.2, 0.02)
        n_large_delta = required_n_paired(0.2, 0.05)

        assert n_large_delta < n_small_delta

    def test_delta_squared_exceeds_p_disc_raises(self) -> None:
        """Δ² >= p_disc raises ValueError."""
        # 0.5² = 0.25 > 0.2
        with pytest.raises(ValueError, match="Δ²"):
            required_n_paired(0.2, 0.5)

    def test_p_disc_zero_raises(self) -> None:
        """p_disc <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="p_disc"):
            required_n_paired(0.0, 0.05)

    def test_p_disc_exceeds_1_raises(self) -> None:
        """p_disc > 1 raises ValueError."""
        with pytest.raises(ValueError, match="p_disc"):
            required_n_paired(1.5, 0.05)

    def test_delta_zero_raises(self) -> None:
        """delta == 0 raises ValueError."""
        with pytest.raises(ValueError, match="delta"):
            required_n_paired(0.2, 0.0)

    def test_alpha_invalid_raises(self) -> None:
        """alpha not in (0, 1) raises ValueError."""
        with pytest.raises(ValueError, match="alpha"):
            required_n_paired(0.2, 0.05, alpha=1.5)

    def test_power_invalid_raises(self) -> None:
        """power not in (0, 1) raises ValueError."""
        with pytest.raises(ValueError, match="power"):
            required_n_paired(0.2, 0.05, power=1.5)

    def test_returns_int(self) -> None:
        """Returns an int."""
        result = required_n_paired(0.2, 0.05)
        assert isinstance(result, int)

    def test_returns_positive(self) -> None:
        """Returns positive int."""
        result = required_n_paired(0.2, 0.05)
        assert result > 0
