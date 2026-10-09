"""Benchmark tests for Rogan-Gladen correction (card S3).

This test validates that corrected_pass_rate runs within acceptable time.
"""

import time

import numpy as np
import pytest

from evalhawk.stats.correction import corrected_pass_rate


@pytest.mark.slow
class TestCorrectionBenchmark:
    """Benchmark: n_test=100_000, n_boot=2000, < 50 ms median."""

    def test_corrected_pass_rate_benchmark(self) -> None:
        """
        Benchmark: median of 5 runs with n_test=100_000, n_boot=2000 < 50 ms.
        """
        # Setup: generate test and calibration data
        rng = np.random.default_rng(42)
        n_test = 100_000
        n_cal = 2000
        n_boot = 2000

        # Generate test data
        judge_test = rng.binomial(1, 0.7, size=n_test).astype(np.int64)

        # Generate calibration data: balanced human labels
        n_pos = n_cal // 2
        n_neg = n_cal - n_pos
        human_cal = np.concatenate(
            [np.ones(n_pos, dtype=np.int64), np.zeros(n_neg, dtype=np.int64)]
        )
        rng.shuffle(human_cal)

        # Generate judge labels with s=0.9, c=0.8
        judge_cal = np.zeros(n_cal, dtype=np.int64)
        judge_cal[human_cal == 1] = (rng.random(n_pos) < 0.9).astype(np.int64)
        judge_cal[human_cal == 0] = (rng.random(n_neg) > 0.8).astype(np.int64)

        # Run 5 times and measure
        times = []
        for _ in range(5):
            rng_boot = np.random.default_rng(43)
            start = time.perf_counter()
            corrected_pass_rate(judge_test, judge_cal, human_cal, rng=rng_boot, n_boot=n_boot)
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        # Median should be < 50 ms
        median_ms = np.median(times) * 1000
        assert median_ms < 50, f"Median time {median_ms:.1f} ms >= 50 ms"
