"""Validation test: McNemar exact vs SciPy reference (card S4).

Compares mcnemar_exact implementation against scipy.stats.binomtest over
5000 random (b, c) pairs to ensure numerical accuracy.
"""

import pytest

from evalhawk.stats.compare import mcnemar_exact

scipy = pytest.importorskip("scipy")  # type: ignore[unused-ignore]


@pytest.mark.slow
def test_mcnemar_exact_vs_scipy_reference() -> None:
    """mcnemar_exact matches scipy.stats.binomtest with rel error < 1e-9."""
    import numpy as np
    from scipy.stats import binomtest

    rng = np.random.default_rng(42)
    b_c_pairs = rng.integers(0, 2001, size=(5000, 2))

    errors = []
    for b_raw, c_raw in b_c_pairs:
        b, c = int(b_raw), int(c_raw)  # mcnemar_exact rejects numpy integer types
        if b + c == 0:
            continue  # Skip zero case

        our_result = mcnemar_exact(b, c)
        scipy_result = binomtest(min(b, c), b + c, 0.5).pvalue

        if scipy_result > 0:
            rel_error = abs(our_result - scipy_result) / scipy_result
            errors.append(rel_error)

    # Check that all errors are below 1e-9
    max_error = max(errors) if errors else 0
    assert max_error < 1e-9, f"Max relative error: {max_error}"
