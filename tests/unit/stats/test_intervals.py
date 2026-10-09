"""Tests for confidence intervals (card S1).

Card S1 implements the Wilson score interval for binomial proportions. The
interval is guaranteed to stay within [0, 1] and is accurate for all sample
sizes and proportions.
"""

import numpy as np
import pytest

from evalhawk.stats.intervals import wilson_interval


# ================================================================ numpy integers
class TestWilsonNumpyIntegers:
    """Counts computed from arrays are NumPy integers and must be accepted."""

    def test_numpy_int_counts_match_python_ints(self) -> None:
        """np.int64 counts give the same Estimate as Python ints."""
        assert wilson_interval(np.int64(82), np.int64(100)) == wilson_interval(82, 100)

    def test_numpy_bool_is_rejected(self) -> None:
        """np.bool_ is rejected like bool."""
        with pytest.raises(ValueError, match="not bool"):
            wilson_interval(np.bool_(True), 10)  # type: ignore[arg-type]


# ================================================================ golden values
class TestWilsonGoldenValues:
    """Known correct values from references and hand calculation."""

    @pytest.mark.parametrize(
        ("k", "n", "expected_low", "expected_high"),
        [
            (82, 100, 0.7333, 0.8830),
            (0, 10, 0.0000, 0.2775),
            (10, 10, 0.7225, 1.0000),
            (500, 1000, 0.4691, 0.5309),
        ],
        ids=[
            "k=82,n=100",
            "k=0,n=10",
            "k=10,n=10",
            "k=500,n=1000",
        ],
    )
    def test_bounds_match_golden_table(
        self, k: int, n: int, expected_low: float, expected_high: float
    ) -> None:
        """Wilson bounds match reference values within tolerance."""
        est = wilson_interval(k, n)
        assert est.low == pytest.approx(expected_low, abs=5e-5)
        assert est.high == pytest.approx(expected_high, abs=5e-5)

    def test_point_estimate_is_sample_proportion(self) -> None:
        """Point estimate equals k / n."""
        est = wilson_interval(82, 100)
        assert est.point == pytest.approx(0.82)

    def test_confidence_0_99_is_wider_than_0_95(self) -> None:
        """Higher confidence level yields wider interval."""
        est_95 = wilson_interval(50, 100, confidence=0.95)
        est_99 = wilson_interval(50, 100, confidence=0.99)
        width_95 = est_95.high - est_95.low
        width_99 = est_99.high - est_99.low
        assert width_99 > width_95


# ================================================================ metadata
class TestWilsonMetadata:
    """Check that returned Estimate has correct metadata."""

    def test_method_is_wilson(self) -> None:
        """method field is 'wilson'."""
        est = wilson_interval(50, 100)
        assert est.method == "wilson"

    def test_n_is_sample_size(self) -> None:
        """n field matches input sample size."""
        est = wilson_interval(50, 100)
        assert est.n == 100

    def test_confidence_is_set(self) -> None:
        """confidence field is set correctly."""
        est = wilson_interval(50, 100, confidence=0.90)
        assert est.confidence == 0.90

    def test_confidence_defaults_to_0_95(self) -> None:
        """confidence defaults to 0.95 when not specified."""
        est = wilson_interval(50, 100)
        assert est.confidence == 0.95

    def test_unknown_rate_defaults_to_zero(self) -> None:
        """unknown_rate defaults to 0.0."""
        est = wilson_interval(50, 100)
        assert est.unknown_rate == 0.0


# ================================================================ string representation
class TestWilsonStringRepresentation:
    """Check __str__ output matches the specified format."""

    def test_str_format_exact_match(self) -> None:
        """String representation matches the exact format."""
        est = wilson_interval(82, 100)
        assert str(est) == "0.820 [0.733, 0.883] (wilson, n=100, unknown=0.0%)"


# ================================================================ error cases
class TestWilsonErrors:
    """Validate that invalid inputs raise ValueError."""

    def test_n_zero_raises(self) -> None:
        """n=0 raises ValueError."""
        with pytest.raises(ValueError, match="n must be >= 1"):
            wilson_interval(0, 0)

    def test_k_negative_raises(self) -> None:
        """k < 0 raises ValueError."""
        with pytest.raises(ValueError, match="k must be in \\[0, n\\]"):
            wilson_interval(-1, 10)

    def test_k_greater_than_n_raises(self) -> None:
        """k > n raises ValueError."""
        with pytest.raises(ValueError, match="k must be in \\[0, n\\]"):
            wilson_interval(11, 10)

    def test_k_bool_raises(self) -> None:
        """k=True raises ValueError (bool check before range check)."""
        with pytest.raises(ValueError, match="k must be int, not bool"):
            wilson_interval(True, 10)  # type: ignore[arg-type]

    def test_n_bool_raises(self) -> None:
        """n=False raises ValueError (bool check before range check)."""
        with pytest.raises(ValueError, match="n must be int, not bool"):
            wilson_interval(5, False)  # type: ignore[arg-type]

    def test_k_float_raises(self) -> None:
        """k as float raises ValueError."""
        with pytest.raises(ValueError, match="k must be int"):
            wilson_interval(5.0, 10)  # type: ignore[arg-type]

    def test_n_float_raises(self) -> None:
        """n as float raises ValueError."""
        with pytest.raises(ValueError, match="n must be int"):
            wilson_interval(5, 10.0)  # type: ignore[arg-type]

    def test_confidence_zero_raises(self) -> None:
        """confidence=0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be strictly between 0 and 1"):
            wilson_interval(5, 10, confidence=0.0)

    def test_confidence_one_raises(self) -> None:
        """confidence=1 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be strictly between 0 and 1"):
            wilson_interval(5, 10, confidence=1.0)

    def test_confidence_negative_raises(self) -> None:
        """confidence < 0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be strictly between 0 and 1"):
            wilson_interval(5, 10, confidence=-0.1)

    def test_confidence_above_one_raises(self) -> None:
        """confidence > 1 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be strictly between 0 and 1"):
            wilson_interval(5, 10, confidence=1.5)


# ================================================================ bounds
class TestWilsonBounds:
    """Verify that bounds satisfy mathematical properties."""

    def test_low_is_nonnegative(self) -> None:
        """low >= 0 for any valid inputs."""
        est = wilson_interval(0, 10)
        assert est.low >= 0.0

    def test_high_is_at_most_one(self) -> None:
        """high <= 1 for any valid inputs."""
        est = wilson_interval(10, 10)
        assert est.high <= 1.0

    def test_low_less_than_or_equal_high(self) -> None:
        """low <= high always."""
        est = wilson_interval(50, 100)
        assert est.low <= est.high

    def test_bounds_narrow_with_larger_sample(self) -> None:
        """Interval width decreases as sample size increases."""
        est_100 = wilson_interval(50, 100)
        est_10000 = wilson_interval(5000, 10000)
        width_100 = est_100.high - est_100.low
        width_10000 = est_10000.high - est_10000.low
        assert width_10000 < width_100

        est = wilson_interval(82, 100)
        result = str(est)
        expected = "0.820 [0.733, 0.883] (wilson, n=100, unknown=0.0%)"
        assert result == expected
