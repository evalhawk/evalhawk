"""Tests for version comparison (card S4).

Tests for McNemar exact test, paired bootstrap, decision logic, and Comparison dataclass.
"""

import numpy as np
import pytest

from evalhawk.core.results import Comparison, Decision, Estimate
from evalhawk.stats.compare import decide, mcnemar_exact, paired_bootstrap


# ================================================================ mcnemar_exact
class TestMcnemarExact:
    """Tests for mcnemar_exact function."""

    def test_mcnemar_exact_known_value_12_30(self) -> None:
        """Known value: mcnemar_exact(12, 30) ≈ 0.00792."""
        result = mcnemar_exact(12, 30)
        assert result == pytest.approx(0.00792, rel=1e-3)

    def test_mcnemar_exact_zero_zero(self) -> None:
        """n=0 returns 1.0."""
        assert mcnemar_exact(0, 0) == 1.0

    def test_mcnemar_exact_equal(self) -> None:
        """b == c returns 1.0."""
        assert mcnemar_exact(7, 7) == 1.0

    def test_mcnemar_exact_symmetric(self) -> None:
        """mcnemar_exact(b, c) == mcnemar_exact(c, b)."""
        result_bc = mcnemar_exact(12, 30)
        result_cb = mcnemar_exact(30, 12)
        assert result_bc == pytest.approx(result_cb)

    def test_mcnemar_exact_zero_ten(self) -> None:
        """mcnemar_exact(0, 10) ≈ 0.001953125."""
        result = mcnemar_exact(0, 10)
        assert result == pytest.approx(0.001953125, rel=1e-6)

    def test_mcnemar_exact_large_case(self) -> None:
        """mcnemar_exact(5000, 5300) returns finite value in (0, 1]."""
        result = mcnemar_exact(5000, 5300)
        assert 0 < result <= 1.0
        assert np.isfinite(result)

    def test_mcnemar_exact_rejects_negative_b(self) -> None:
        """Negative b raises ValueError."""
        with pytest.raises(ValueError, match="b"):
            mcnemar_exact(-1, 5)

    def test_mcnemar_exact_rejects_negative_c(self) -> None:
        """Negative c raises ValueError."""
        with pytest.raises(ValueError, match="c"):
            mcnemar_exact(5, -1)

    def test_mcnemar_exact_rejects_bool_b(self) -> None:
        """Bool b raises ValueError."""
        with pytest.raises(ValueError, match="b"):
            mcnemar_exact(True, 5)  # type: ignore[arg-type]

    def test_mcnemar_exact_rejects_bool_c(self) -> None:
        """Bool c raises ValueError."""
        with pytest.raises(ValueError, match="c"):
            mcnemar_exact(5, True)  # type: ignore[arg-type]


# ================================================================ paired_bootstrap
class TestPairedBootstrap:
    """Tests for paired_bootstrap function."""

    def test_paired_bootstrap_identical_arrays(self) -> None:
        """Identical a and b give point 0.0 and interval [0, 0]."""
        a = np.array([0, 1, 0, 1, 1])
        b = np.array([0, 1, 0, 1, 1])
        rng = np.random.default_rng(42)
        result = paired_bootstrap(a, b, rng=rng, n_boot=100)
        assert result.point == pytest.approx(0.0)
        assert result.low == pytest.approx(0.0)
        assert result.high == pytest.approx(0.0)

    def test_paired_bootstrap_all_zeros_to_all_ones(self) -> None:
        """a all 0, b all 1 gives point 1.0."""
        a = np.array([0, 0, 0, 0, 0])
        b = np.array([1, 1, 1, 1, 1])
        rng = np.random.default_rng(42)
        result = paired_bootstrap(a, b, rng=rng, n_boot=100)
        assert result.point == pytest.approx(1.0)

    def test_paired_bootstrap_reproducible_with_seed(self) -> None:
        """Same seed produces same result."""
        a = np.array([0, 1, 0, 1])
        b = np.array([1, 1, 0, 0])

        rng1 = np.random.default_rng(42)
        result1 = paired_bootstrap(a, b, rng=rng1, n_boot=100)

        rng2 = np.random.default_rng(42)
        result2 = paired_bootstrap(a, b, rng=rng2, n_boot=100)

        assert result1.point == result2.point
        assert result1.low == result2.low
        assert result1.high == result2.high

    def test_paired_bootstrap_length_mismatch(self) -> None:
        """Length mismatch raises ValueError."""
        a = np.array([0, 1, 0])
        b = np.array([1, 1])
        rng = np.random.default_rng(42)
        with pytest.raises(ValueError, match="length"):
            paired_bootstrap(a, b, rng=rng, n_boot=100)

    def test_paired_bootstrap_large_input(self) -> None:
        """Large input (n=100_000, n_boot=2000) completes without memory error."""
        a = np.random.default_rng(42).binomial(1, 0.5, size=100_000)
        b = np.random.default_rng(43).binomial(1, 0.5, size=100_000)
        rng = np.random.default_rng(44)
        result = paired_bootstrap(a, b, rng=rng, n_boot=2000)
        assert np.isfinite(result.point)
        assert np.isfinite(result.low)
        assert np.isfinite(result.high)

    def test_paired_bootstrap_method_name(self) -> None:
        """Method is 'paired_bootstrap'."""
        a = np.array([0, 1, 0])
        b = np.array([1, 1, 0])
        rng = np.random.default_rng(42)
        result = paired_bootstrap(a, b, rng=rng, n_boot=100)
        assert result.method == "paired_bootstrap"

    def test_paired_bootstrap_n_is_pairs(self) -> None:
        """n field is the number of pairs."""
        a = np.array([0, 1, 0, 1, 1])
        b = np.array([1, 1, 0, 1, 0])
        rng = np.random.default_rng(42)
        result = paired_bootstrap(a, b, rng=rng, n_boot=100)
        assert result.n == 5


# ================================================================ decide
class TestDecide:
    """Tests for decide function."""

    def test_decide_better(self) -> None:
        """low > 0 returns BETTER."""
        diff = Estimate(
            point=0.1, low=0.05, high=0.15, n=100, method="test"
        )
        assert decide(diff) == "BETTER"

    def test_decide_worse(self) -> None:
        """high < 0 returns WORSE."""
        diff = Estimate(
            point=-0.1, low=-0.15, high=-0.05, n=100, method="test"
        )
        assert decide(diff) == "WORSE"

    def test_decide_inconclusive(self) -> None:
        """Interval spanning 0 returns INCONCLUSIVE."""
        diff = Estimate(
            point=0.0, low=-0.1, high=0.1, n=100, method="test"
        )
        assert decide(diff) == "INCONCLUSIVE"

    def test_decide_low_equals_zero(self) -> None:
        """low == 0 returns INCONCLUSIVE."""
        diff = Estimate(
            point=0.05, low=0.0, high=0.1, n=100, method="test"
        )
        assert decide(diff) == "INCONCLUSIVE"

    def test_decide_high_equals_zero(self) -> None:
        """high == 0 returns INCONCLUSIVE."""
        diff = Estimate(
            point=-0.05, low=-0.1, high=0.0, n=100, method="test"
        )
        assert decide(diff) == "INCONCLUSIVE"



# ================================================================ Comparison class
class TestComparison:
    """Tests for Comparison dataclass."""

    def test_comparison_valid(self) -> None:
        """Valid Comparison is created."""
        diff = Estimate(
            point=0.04, low=-0.01, high=0.09, n=42, method="paired_bootstrap"
        )
        comp = Comparison(
            difference=diff, p_value=0.210, b=12, c=30, decision="INCONCLUSIVE"
        )
        assert comp.difference is diff
        assert comp.p_value == 0.210
        assert comp.b == 12
        assert comp.c == 30
        assert comp.decision == "INCONCLUSIVE"

    def test_comparison_frozen(self) -> None:
        """Comparison is frozen."""
        diff = Estimate(
            point=0.04, low=-0.01, high=0.09, n=42, method="paired_bootstrap"
        )
        comp = Comparison(
            difference=diff, p_value=0.210, b=12, c=30, decision="INCONCLUSIVE"
        )
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            comp.p_value = 0.3  # type: ignore[misc]

    def test_comparison_slots(self) -> None:
        """Comparison uses slots."""
        diff = Estimate(
            point=0.04, low=-0.01, high=0.09, n=42, method="paired_bootstrap"
        )
        comp = Comparison(
            difference=diff, p_value=0.210, b=12, c=30, decision="INCONCLUSIVE"
        )
        with pytest.raises((AttributeError, TypeError)):
            comp.custom_field = "value"  # type: ignore[attr-defined]

    def test_comparison_invalid_p_value_too_high(self) -> None:
        """p_value > 1 raises ValueError."""
        diff = Estimate(
            point=0.04, low=-0.01, high=0.09, n=42, method="paired_bootstrap"
        )
        with pytest.raises(ValueError, match="p_value"):
            Comparison(
                difference=diff, p_value=1.5, b=12, c=30, decision="INCONCLUSIVE"
            )

    def test_comparison_invalid_p_value_negative(self) -> None:
        """p_value < 0 raises ValueError."""
        diff = Estimate(
            point=0.04, low=-0.01, high=0.09, n=42, method="paired_bootstrap"
        )
        with pytest.raises(ValueError, match="p_value"):
            Comparison(
                difference=diff, p_value=-0.1, b=12, c=30, decision="INCONCLUSIVE"
            )

    def test_comparison_invalid_b_negative(self) -> None:
        """b < 0 raises ValueError."""
        diff = Estimate(
            point=0.04, low=-0.01, high=0.09, n=42, method="paired_bootstrap"
        )
        with pytest.raises(ValueError, match="b"):
            Comparison(
                difference=diff, p_value=0.210, b=-1, c=30, decision="INCONCLUSIVE"
            )

    def test_comparison_invalid_c_negative(self) -> None:
        """c < 0 raises ValueError."""
        diff = Estimate(
            point=0.04, low=-0.01, high=0.09, n=42, method="paired_bootstrap"
        )
        with pytest.raises(ValueError, match="c"):
            Comparison(
                difference=diff, p_value=0.210, b=12, c=-1, decision="INCONCLUSIVE"
            )

    def test_comparison_str_format_signed(self) -> None:
        """__str__ uses signed format."""
        diff = Estimate(
            point=0.04, low=-0.01, high=0.09, n=42, method="paired_bootstrap"
        )
        comp = Comparison(
            difference=diff, p_value=0.210, b=12, c=30, decision="INCONCLUSIVE"
        )
        result = str(comp)
        # Expected: "+0.040 [-0.010, +0.090] INCONCLUSIVE (p=0.210, b=12, c=30)"
        assert "+0.040" in result
        assert "[-0.010, +0.090]" in result
        assert "INCONCLUSIVE" in result
        assert "p=0.210" in result
        assert "b=12" in result
        assert "c=30" in result

    def test_comparison_str_negative_difference(self) -> None:
        """__str__ formats negative differences correctly."""
        diff = Estimate(
            point=-0.04, low=-0.09, high=0.01, n=42, method="paired_bootstrap"
        )
        comp = Comparison(
            difference=diff, p_value=0.050, b=30, c=12, decision="WORSE"
        )
        result = str(comp)
        assert "-0.040" in result
        assert "[-0.090, +0.010]" in result
