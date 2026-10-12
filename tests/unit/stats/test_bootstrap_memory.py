"""Check bootstrap batches without retaining every resample."""

import tracemalloc
from typing import cast

import numpy as np
import pytest

from evalhawk.stats.clustered import cluster_bootstrap_means
from evalhawk.stats.compare import paired_bootstrap


def test_cluster_batches_obey_small_memory_budget() -> None:
    values = np.tile([0.0, 1.0], 10_000)
    clusters = np.arange(len(values), dtype=np.int32)
    tracemalloc.start()
    try:
        result = cluster_bootstrap_means(
            values,
            clusters,
            rng=np.random.default_rng(0),
            n_boot=100,
            memory_budget_bytes=1024 * 1024,
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.shape == (100,)
    assert peak < 4 * 1024 * 1024
    assert abs(float(result.mean()) - 0.5) < 0.01


@pytest.mark.slow
@pytest.mark.parametrize("clustered", [False, True])
def test_million_item_bootstrap_peak_is_bounded(clustered: bool) -> None:
    values = np.tile(np.array([0, 1], dtype=np.int8), 500_000)
    clusters = np.arange(len(values), dtype=np.int32)
    tracemalloc.start()
    try:
        if clustered:
            result = cluster_bootstrap_means(
                values,
                clusters,
                rng=np.random.default_rng(0),
                n_boot=100,
            )
            assert abs(float(result.mean()) - 0.5) < 0.01
        else:
            difference = paired_bootstrap(
                values, 1 - values, rng=np.random.default_rng(0), n_boot=100
            )
            assert abs(difference.point) < 0.01
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 160 * 1024 * 1024


def test_memory_budget_requires_integer() -> None:
    with pytest.raises(ValueError, match="integer"):
        cluster_bootstrap_means(
            [0, 1],
            [0, 1],
            rng=np.random.default_rng(0),
            n_boot=100,
            memory_budget_bytes=cast(int, 1.5),
        )
