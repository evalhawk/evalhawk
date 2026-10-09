# S4 · Version comparison (v1 vs v2)

- **Author:** Krishna Nandimandalam
- **Date:** 2026-10-09
- **Card:** [#8](../development/workplan.md) · **PR:** #TBD

## What I built

In `stats/compare.py`: `mcnemar_exact(b, c)`, `paired_bootstrap(a, b, *, rng, n_boot, confidence, clusters=None)`
and `decide(diff)`. In `core/results.py`: `Decision` and the `Comparison` value object.
`experiments/benchmarks/mcnemar_vs_scipy.py` compares our p-value with SciPy's.

## The idea, simply

Run v1 and v2 on the same questions. Questions both get right (or both get wrong) tell us nothing
about which version is better; only the disagreements do. Count `b` (v1 pass, v2 fail) and `c`
(v1 fail, v2 pass). If the versions were equally good, each disagreement would be a coin flip,
so `b` follows a Binomial(b + c, 0.5). The p-value is how surprising the observed split is.

## How I know it's right

- `mcnemar_exact(12, 30)` ≈ 0.00792; `b = c` gives 1.0; `(0, 10)` gives 2·0.5¹⁰.
- A slow test matches `scipy.stats.binomtest` to a relative error below 1e-9 on 5,000 random cases.
- `decide` is tested on BETTER, WORSE, INCONCLUSIVE and the boundary where `low == 0`.
- Not run yet: tests are written but the maintainer runs them.

## What surprised me / gotchas

- The p-value is summed in log space (`log-sum-exp`), so there are no huge binomial coefficients.
- `paired_bootstrap` resamples example indices, as the card says, in chunks of 100 resamples so a
  100k-item input does not need gigabytes at once.
- With `clusters=`, whole clusters are resampled instead (shared helper in `stats/clustered.py`).

## How AI helped (and where it was wrong)

_To be filled in by the author._

## Learn more

- McNemar (1947), *Note on the sampling error of the difference between correlated proportions*.
- Miller (2024), *Adding Error Bars to Evals* (arXiv 2411.00640).
- Architecture §13.4.