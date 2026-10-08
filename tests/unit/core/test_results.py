"""Tests for the Estimate result value object (card J1).

Estimate is the universal value object for any reportable statistics result: the
point estimate, its error range, sample size, method used to compute it, and unknown
rate. It enforces only that low <= high and all values are finite and in range.
"""

import dataclasses
import math

import pytest

from evalhawk.core.results import Comparison, Decision, Estimate

# ================================================================ fixtures
BASELINE = Estimate(
    point=0.82,
    low=0.7333,
    high=0.8830,
    n=100,
    method="wilson",
)


# ================================================================ valid values
def test_defaults_are_95_percent_confidence_and_no_unknowns() -> None:
    """Unspecified confidence and unknown_rate take their defaults."""
    est = Estimate(point=0.5, low=0.4, high=0.6, n=10, method="test")
    assert est.confidence == 0.95
    assert est.unknown_rate == 0.0


def test_width_is_high_minus_low() -> None:
    """width property computes the interval width."""
    assert BASELINE.width == pytest.approx(0.1497)


def test_zero_width_interval_is_allowed() -> None:
    """point and low and high can all be equal."""
    est = Estimate(point=0.5, low=0.5, high=0.5, n=1, method="test")
    assert est.width == pytest.approx(0.0)


def test_point_outside_interval_is_allowed() -> None:
    """Point containment is not enforced (bootstrap decision D2)."""
    # Point 0.9 is outside [0.7, 0.85]
    est = Estimate(point=0.9, low=0.7, high=0.85, n=100, method="bootstrap")
    assert est.point == 0.9
    assert est.low < est.point or est.point > est.high  # Point is outside


def test_negative_values_are_allowed_for_differences() -> None:
    """Differences and kappa can be negative."""
    # Difference of -0.04 in interval [-0.09, 0.01]
    est = Estimate(point=-0.04, low=-0.09, high=0.01, n=100, method="paired")
    assert est.point == -0.04
    assert est.low < 0 < est.high or est.high < 0


def test_n_zero_is_allowed() -> None:
    """n=0 is allowed by the Estimate object itself."""
    est = Estimate(point=0.5, low=0.4, high=0.6, n=0, method="test")
    assert est.n == 0


def test_unknown_rate_bounds_are_inclusive() -> None:
    """unknown_rate=0.0 and unknown_rate=1.0 are both allowed."""
    est_zero = Estimate(
        point=0.5, low=0.4, high=0.6, n=10, method="test", unknown_rate=0.0
    )
    est_one = Estimate(
        point=0.5, low=0.4, high=0.6, n=10, method="test", unknown_rate=1.0
    )
    assert est_zero.unknown_rate == 0.0
    assert est_one.unknown_rate == 1.0


# ================================================================ invalid values
@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"point": math.nan}, "point"),
        ({"point": math.inf}, "point"),
        ({"point": -math.inf}, "point"),
        ({"low": math.nan}, "low"),
        ({"low": -math.inf}, "low"),
        ({"high": math.nan}, "high"),
        ({"high": math.inf}, "high"),
        ({"confidence": math.nan}, "confidence"),
        ({"confidence": 0.0}, "confidence"),
        ({"confidence": 1.0}, "confidence"),
        ({"confidence": 1.5}, "confidence"),
        ({"confidence": -0.1}, "confidence"),
        ({"unknown_rate": -0.1}, "unknown_rate"),
        ({"unknown_rate": 1.1}, "unknown_rate"),
        ({"unknown_rate": math.nan}, "unknown_rate"),
        ({"low": 0.9, "high": 0.7}, "low.*high"),  # low > high
        ({"n": -1}, "n"),
        ({"method": ""}, "method"),
        ({"method": "  "}, "method"),
    ],
    ids=[
        "point_nan",
        "point_inf",
        "point_-inf",
        "low_nan",
        "low_-inf",
        "high_nan",
        "high_inf",
        "confidence_nan",
        "confidence_0.0",
        "confidence_1.0",
        "confidence_1.5",
        "confidence_-0.1",
        "unknown_rate_-0.1",
        "unknown_rate_1.1",
        "unknown_rate_nan",
        "low_above_high",
        "negative_n",
        "empty_method",
        "blank_method",
    ],
)
def test_invalid_values_raise_value_error(override: dict, match: str) -> None:
    """Invalid field values raise ValueError with descriptive messages."""
    with pytest.raises(ValueError, match=match):
        dataclasses.replace(BASELINE, **override)


def test_error_message_names_the_field() -> None:
    """Error messages name the field and show the offending value."""
    with pytest.raises(ValueError, match="n.*-1"):
        Estimate(point=0.5, low=0.4, high=0.6, n=-1, method="test")


# ================================================================ immutability
def test_fields_cannot_be_changed() -> None:
    """Estimate is frozen: fields cannot be reassigned."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        BASELINE.point = 0.5  # pyright: ignore[reportAttributeAccessIssue]


def test_new_attributes_cannot_be_added() -> None:
    """Estimate uses slots: new attributes cannot be added."""
    with pytest.raises((AttributeError, TypeError)):
        BASELINE.custom_field = "value"  # pyright: ignore[reportAttributeAccessIssue]


def test_positional_arguments_are_rejected() -> None:
    """Estimate is keyword-only: positional arguments raise TypeError."""
    # pyright: ignore[reportCallIssue]
    with pytest.raises(TypeError):
        Estimate(0.82, 0.7333, 0.8830, 100, "wilson")  # type: ignore[call-arg]


# ================================================================ equality and hashing
def test_equal_estimates_compare_equal_and_hash_equal() -> None:
    """Two Estimates with the same values are equal and have the same hash."""
    est1 = Estimate(
        point=0.82, low=0.7333, high=0.8830, n=100, method="wilson"
    )
    est2 = Estimate(
        point=0.82, low=0.7333, high=0.8830, n=100, method="wilson"
    )
    assert est1 == est2
    assert hash(est1) == hash(est2)


# ================================================================ string representation
def test_str_matches_card_format() -> None:
    """__str__ produces the exact format specified in the card."""
    result = str(BASELINE)
    expected = "0.820 [0.733, 0.883] (wilson, n=100, unknown=0.0%)"
    assert result == expected


def test_str_shows_unknown_rate_as_percentage() -> None:
    """unknown_rate is shown as a percentage in __str__."""
    est = Estimate(
        point=0.5,
        low=0.4,
        high=0.6,
        n=100,
        method="test",
        unknown_rate=0.125,
    )
    result = str(est)
    # Should end with "unknown=12.5%)"



# ================================================================ Comparison (S4)
class TestComparison:
    """Tests for Comparison dataclass (card S4)."""

    def test_comparison_valid_all_fields(self) -> None:
        """Valid Comparison is created with all required fields."""
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
        with pytest.raises(dataclasses.FrozenInstanceError):
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

    @pytest.mark.parametrize(
        ("p_value", "b", "c", "match_field"),
        [
            (1.5, 12, 30, "p_value"),
            (-0.1, 12, 30, "p_value"),
            (0.210, -1, 30, "b"),
            (0.210, 12, -1, "c"),
        ],
        ids=["p_value_too_high", "p_value_negative", "b_negative", "c_negative"],
    )
    def test_comparison_invalid_values(
        self, p_value: float, b: int, c: int, match_field: str
    ) -> None:
        """Invalid field values raise ValueError."""
        diff = Estimate(
            point=0.04, low=-0.01, high=0.09, n=42, method="paired_bootstrap"
        )
        with pytest.raises(ValueError, match=match_field):
            Comparison(
                difference=diff, p_value=p_value, b=b, c=c, decision="INCONCLUSIVE"
            )

    def test_comparison_str_format_signed(self) -> None:
        """__str__ uses signed format: +0.040 [-0.010, +0.090]."""
        diff = Estimate(
            point=0.04, low=-0.01, high=0.09, n=42, method="paired_bootstrap"
        )
        comp = Comparison(
            difference=diff, p_value=0.210, b=12, c=30, decision="INCONCLUSIVE"
        )
        result = str(comp)
        # Exact format: "+0.040 [-0.010, +0.090] INCONCLUSIVE (p=0.210, b=12, c=30)"
        assert "+0.040" in result
        assert "[-0.010, +0.090]" in result
        assert "INCONCLUSIVE" in result
        assert "p=0.210" in result
        assert "b=12" in result
        assert "c=30" in result

    def test_comparison_str_negative_difference(self) -> None:
        """__str__ formats negative differences with minus sign."""
        diff = Estimate(
            point=-0.04, low=-0.09, high=0.01, n=42, method="paired_bootstrap"
        )
        comp = Comparison(
            difference=diff, p_value=0.050, b=30, c=12, decision="WORSE"
        )
        result = str(comp)
        assert "-0.040" in result
        assert "[-0.090, +0.010]" in result

    assert "unknown=12.5%)" in result
