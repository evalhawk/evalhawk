"""Property-based tests for judge agreement metrics (card S2).

Uses Hypothesis for property testing with fixed seeds for reproducibility.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from evalhawk.stats.agreement import cohen_kappa, confusion

# Both classes with at least 5 items each, so degenerate bootstrap resamples stay rare.
_BOTH_CLASSES = st.lists(st.integers(0, 1), min_size=20, max_size=100).filter(
    lambda x: 5 <= sum(x) <= len(x) - 5
)
_PAIRS = st.lists(st.tuples(st.integers(0, 1), st.integers(0, 1)), min_size=20, max_size=100)


# ================================================== perfect judge property
class TestPerfectJudgeProperty:
    """Property: perfect judge (judge == human) has kappa = 1.0."""

    @given(human=_BOTH_CLASSES)
    @settings(derandomize=True)
    def test_perfect_judge_kappa_is_one(self, human: list[int]) -> None:
        """Perfect judge (judge == human) yields kappa = 1.0."""
        rng = np.random.default_rng(42)
        est = cohen_kappa(human, human, rng=rng, n_boot=2000)
        assert est.point == pytest.approx(1.0, abs=1e-6)


# ================================================== interval properties
class TestKappaIntervalProperties:
    """Property: kappa interval is valid and well-formed."""

    @given(pairs=_PAIRS)
    @settings(derandomize=True)
    def test_kappa_low_le_high(self, pairs: list[tuple[int, int]]) -> None:
        """Kappa interval: low <= high always."""
        human = [p[0] for p in pairs]
        judge = [p[1] for p in pairs]
        try:
            est = cohen_kappa(human, judge, rng=np.random.default_rng(42), n_boot=100)
        except ValueError:
            return  # kappa undefined or too many degenerate resamples for this sample
        assert est.low <= est.high

    @given(pairs=_PAIRS)
    @settings(derandomize=True)
    def test_kappa_within_bounds(self, pairs: list[tuple[int, int]]) -> None:
        """Kappa interval within [-1, 1]."""
        human = [p[0] for p in pairs]
        judge = [p[1] for p in pairs]
        try:
            est = cohen_kappa(human, judge, rng=np.random.default_rng(42), n_boot=100)
        except ValueError:
            return  # kappa undefined or too many degenerate resamples for this sample
        assert est.low >= -1.0
        assert est.high <= 1.0


# ================================================== order independence
class TestConfusionOrderIndependence:
    """Property: confusion matrix is order-independent."""

    @given(pairs=_PAIRS, data=st.data())
    @settings(derandomize=True)
    def test_confusion_order_independent(
        self, pairs: list[tuple[int, int]], data: st.DataObject
    ) -> None:
        """Shuffling item order doesn't change confusion."""
        c1 = confusion([p[0] for p in pairs], [p[1] for p in pairs])

        shuffled = data.draw(st.permutations(pairs))
        c2 = confusion([p[0] for p in shuffled], [p[1] for p in shuffled])

        assert c1 == c2
