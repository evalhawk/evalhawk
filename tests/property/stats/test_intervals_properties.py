"""Property-based tests for confidence intervals using Hypothesis (card S1)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from evalhawk.stats.intervals import wilson_interval


def _k_n(max_n: int, *, interior: bool = False) -> st.SearchStrategy[tuple[int, int]]:
    """Draw (k, n) with k <= n; interior=True keeps 0 < k < n."""
    min_n = 2 if interior else 1
    return st.integers(min_value=min_n, max_value=max_n).flatmap(
        lambda n: st.tuples(
            st.integers(min_value=1 if interior else 0, max_value=n - 1 if interior else n),
            st.just(n),
        )
    )


# Use derandomize=True to get fixed seeds for reproducibility
@given(kn=_k_n(10000), confidence=st.floats(min_value=0.8, max_value=0.99))
@settings(derandomize=True)
def test_bounds_within_unit_interval(kn: tuple[int, int], confidence: float) -> None:
    """0 <= low <= point <= high <= 1 for all valid inputs."""
    k, n = kn
    est = wilson_interval(k, n, confidence=confidence)
    assert est.low >= 0.0
    assert est.low <= est.point
    assert est.point <= est.high
    assert est.high <= 1.0


@given(kn=_k_n(10000))
@settings(derandomize=True)
def test_symmetry_property(kn: tuple[int, int]) -> None:
    """low(k, n) ≈ 1 - high(n - k, n)."""
    k, n = kn
    est_k = wilson_interval(k, n)
    est_complement = wilson_interval(n - k, n)
    assert est_k.low == pytest.approx(1.0 - est_complement.high, abs=1e-10)
    assert est_k.high == pytest.approx(1.0 - est_complement.low, abs=1e-10)


@given(kn=_k_n(100, interior=True))
@settings(derandomize=True, max_examples=200)
def test_narrowing_property(kn: tuple[int, int]) -> None:
    """Interval is strictly narrower when sample size increases 10x at a fixed rate."""
    k, n = kn
    est_small = wilson_interval(k, n)
    est_large = wilson_interval(10 * k, 10 * n)
    assert est_large.width < est_small.width
