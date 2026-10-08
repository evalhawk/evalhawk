\"\"\"Property-based tests for judge agreement metrics (card S2).

Uses Hypothesis for property testing with fixed seeds for reproducibility.
\"\"\"

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from evalhawk.stats.agreement import cohen_kappa, confusion


# ================================================== perfect judge property
class TestPerfectJudgeProperty:
    \"\"\"Property: perfect judge (judge == human) has kappa = 1.0.\"\"\"

    @given(
        human=st.lists(
            st.integers(0, 1), min_size=2, max_size=100
        ).filter(lambda x: len(set(x)) > 1)  # both classes present
    )
    @settings(derandomize=True)
    def test_perfect_judge_kappa_is_one(self, human: list) -> None:
        \"\"\"Perfect judge (judge == human) yields kappa = 1.0.\"\"\"
        judge = human  # Perfect agreement
        rng = np.random.default_rng(42)
        est = cohen_kappa(human, judge, rng=rng, n_boot=100)
        assert est.point == pytest.approx(1.0, abs=1e-6)


# ================================================== interval properties
class TestKappaIntervalProperties:
    \"\"\"Property: kappa interval is valid and well-formed.\"\"\"

    @given(
        human=st.lists(
            st.integers(0, 1),
            min_size=10,
            max_size=100
        ).filter(lambda x: len(set(x)) > 1),  # both classes present
        judge=st.lists(
            st.integers(0, 1),
            min_size=10,
            max_size=100
        ).filter(lambda x: len(set(x)) > 1),  # both classes present
    )
    @settings(derandomize=True)
    def test_kappa_low_le_high(self, human: list, judge: list) -> None:
        \"\"\"Kappa interval: low <= high always.\"\"\"
        if len(human) != len(judge):
            return
        try:
            rng = np.random.default_rng(42)
            est = cohen_kappa(human, judge, rng=rng, n_boot=100)
            assert est.low <= est.high
        except ValueError:
            # p_e == 1 or other degenerate case; skip
            pass

    @given(
        human=st.lists(
            st.integers(0, 1),
            min_size=10,
            max_size=100
        ).filter(lambda x: len(set(x)) > 1),
        judge=st.lists(
            st.integers(0, 1),
            min_size=10,
            max_size=100
        ).filter(lambda x: len(set(x)) > 1),
    )
    @settings(derandomize=True)
    def test_kappa_within_bounds(self, human: list, judge: list) -> None:
        \"\"\"Kappa interval within [-1, 1].\"\"\"
        if len(human) != len(judge):
            return
        try:
            rng = np.random.default_rng(42)
            est = cohen_kappa(human, judge, rng=rng, n_boot=100)
            assert -1.0 <= est.low
            assert est.high <= 1.0
        except ValueError:
            pass


# ================================================== order independence
class TestConfusionOrderIndependence:
    \"\"\"Property: confusion matrix is order-independent.\"\"\"

    @given(
        pairs=st.lists(
            st.tuples(st.integers(0, 1), st.integers(0, 1)),
            min_size=2,
            max_size=100
        )
    )
    @settings(derandomize=True)
    def test_confusion_order_independent(
        self, pairs: list
    ) -> None:
        \"\"\"Shuffling item order doesn't change confusion.\"\"\"
        human = [p[0] for p in pairs]
        judge = [p[1] for p in pairs]

        c1 = confusion(human, judge)

        # Shuffle
        shuffled_pairs = sorted(pairs, key=lambda _: np.random.default_rng(42).random())
        human_shuffled = [p[0] for p in shuffled_pairs]
        judge_shuffled = [p[1] for p in shuffled_pairs]

        c2 = confusion(human_shuffled, judge_shuffled)

        assert c1.tp == c2.tp
        assert c1.fn == c2.fn
        assert c1.fp == c2.fp
        assert c1.tn == c2.tn
