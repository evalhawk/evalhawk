"""Property-based tests for confidence intervals using Hypothesis (card S1)."""

import pytest
from hypothesis import given, settings, strategies as st

from evalhawk.stats.intervals import wilson_interval


# Use derandomize=True to get fixed seeds for reproducibility
@given(
    k=st.integers(min_value=0, max_value=10000),
    n=st.integers(min_value=1, max_value=10000),
    confidence=st.floats(min_value=0.8, max_value=0.99),
)
@settings(derandomize=True)
def test_bounds_within_unit_interval(
    k: int, n: int, confidence: float
) -> None:
    """0 <= low <= high <= 1 for all valid inputs."""
    if k > n:
        # k must be <= n
        return
    est = wilson_interval(k, n, confidence=confidence)
    assert 0.0 <= est.low
    assert est.low <= est.high
    assert est.high <= 1.0


@given(
    k=st.integers(min_value=0, max_value=10000),
    n=st.integers(min_value=1, max_value=10000),
)
@settings(derandomize=True)
def test_symmetry_property(k: int, n: int) -> None:
    """low(k, n) ≈ 1 - high(n - k, n)."""
    if k > n:
        return
    est_k = wilson_interval(k, n)
    est_complement = wilson_interval(n - k, n)
    # Symmetry: interval for k should mirror interval for n-k
    # low(k) should equal 1 - high(n-k)
    assert est_k.low == pytest.approx(1.0 - est_complement.high, abs=1e-10)
    assert est_k.high == pytest.approx(1.0 - est_complement.low, abs=1e-10)


@given(
    k=st.integers(min_value=1, max_value=100),
    n=st.integers(min_value=1, max_value=100),
)
@settings(derandomize=True, max_examples=200)
def test_narrowing_property(k: int, n: int) -> None:
    """Interval is strictly narrower when sample size increases 10x."""
    if k == 0 or k == n:
        # Skip degenerate cases
        return
    est_small = wilson_interval(k, n)
    est_large = wilson_interval(10 * k, 10 * n)
    width_small = est_small.high - est_small.low
    width_large = est_large.high - est_large.low
    # Larger sample should have narrower interval
    assert width_large < width_small
