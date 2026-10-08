# S7 · Coverage simulation

- **Author:** AI Assistant
- **Date:** 2026-10-09
- **Card:** [#19 · S7](../development/workplan.md) · **PR:** pending

## What I built

Fixed-seed, slow coverage simulations for naive Wilson, Rogan–Gladen, PPI,
cluster-robust human-score intervals, and clustered Rogan–Gladen intervals.
A standalone script repeats the simulations over θ = 0.1 … 0.9 and writes
`experiments/figures/coverage_naive_vs_corrected.png` when the maintainer runs it.

The test and script each keep private simulation helpers; tests never import
from `experiments/`. The experiments dependency group uses `matplotlib>=3.11.2`,
looked up on PyPI. `uv.lock` is untouched.

## The idea, simply

A 95% interval promises that 95% of intervals built this way contain the truth.
Generate thousands of worlds where the truth is known, build an interval in each,
and count how often it contains that truth: coverage = containing intervals / replicates.

Judge errors bias naive intervals. Correcting the judge addresses that bias;
accounting for clusters addresses the extra uncertainty from related test items.
With κ = 4, ICC = 1/(κ+1) = 0.2 and the ten-item design effect is 2.8.

## How I know it's right

Tests are written, not run. Coverage results and laptop runtime remain unmeasured.
Each method uses 2000 replicates at θ ∈ {0.5, 0.8}, sensitivity 0.9,
specificity 0.8, 500 iid calibration items, and 2000 test items.
Clustered worlds have 200 clusters of ten items with beta-distributed pass rates.
Bootstraps use 1000 resamples and independent fixed-seed random streams.

Corrected coverage is asserted within [0.935, 0.965], naive coverage below 0.80,
and unclustered comparisons on the same clustered data below 0.90.
Vectorized world generation avoids Python loops over individual items;
existing statistics functions are called without modification.

**Chart placeholder:** embed `coverage_naive_vs_corrected.png` here after generation.

## What surprised me / gotchas

Rogan–Gladen percentile bootstraps may under-cover with small calibration sets or
θ near zero or one. If the maintainer observes coverage outside 93.5–96.5%,
record the setting and measured coverage here and in `docs/limitations.md`;
do not loosen the band. Do not drop or retry failing replicates.
The ±1.5-point band reflects approximately three Monte Carlo standard errors
at 2000 replicates; lower `--reps` values are exploratory only.

## How AI helped (and where it was wrong)

<!-- Maintainer to fill in. -->

## Learn more

- [Matplotlib on PyPI](https://pypi.org/project/matplotlib/)
- [Rogan and Gladen (1978)](https://doi.org/10.1093/aje/107.1.71)
- [Prediction-powered inference](https://doi.org/10.1126/science.adi6000)
