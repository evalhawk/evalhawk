"""Benchmark: mcnemar_exact vs scipy.stats.binomtest (card S4, ADR-0009).

Compares speed and accuracy of the pure-NumPy mcnemar_exact against
scipy.stats.binomtest on random test cases. Written only; not run here.
"""

import time

import numpy as np

from evalhawk.stats.compare import mcnemar_exact

scipy = __import__("scipy", fromlist=["stats"])


def benchmark_mcnemar_vs_scipy(n_cases: int = 1000) -> None:
    """Benchmark mcnemar_exact vs scipy.stats.binomtest.

    Args:
        n_cases: Number of random (b, c) pairs to test.
    """
    rng = np.random.default_rng(42)
    b_c_pairs = rng.integers(0, 2001, size=(n_cases, 2))

    # Benchmark our implementation
    start = time.perf_counter()
    our_results = [mcnemar_exact(int(b), int(c)) for b, c in b_c_pairs]
    our_time = time.perf_counter() - start

    # Benchmark scipy
    start = time.perf_counter()
    scipy_results = [
        scipy.stats.binomtest(min(int(b), int(c)), int(b) + int(c), 0.5).pvalue
        for b, c in b_c_pairs
    ]
    scipy_time = time.perf_counter() - start

    # Compute relative errors
    max_rel_error = 0.0
    for our, sp in zip(our_results, scipy_results, strict=True):
        if sp > 0:
            rel_error = abs(our - sp) / sp
            max_rel_error = max(max_rel_error, rel_error)

    # Print results
    speed_up = scipy_time / our_time
    print(f"Cases: {n_cases}")
    print(f"Our time: {our_time:.4f}s")
    print(f"SciPy time: {scipy_time:.4f}s")
    print(f"Speed-up: {speed_up:.2f}x")
    print(f"Max relative error: {max_rel_error:.2e}")


if __name__ == "__main__":
    benchmark_mcnemar_vs_scipy(1000)
