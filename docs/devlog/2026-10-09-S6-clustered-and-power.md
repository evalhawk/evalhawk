# S6 · Clustered errors and "need N more"

- **Author:** Krishna Nandimandalam
- **Date:** 2026-10-09
- **Card:** [#10](../development/workplan.md) · **PR:** #TBD

## What I built

- `stats/clustered.py`: `cluster_robust_se`, `clustered_mean_interval` and `cluster_bootstrap_means`
- `stats/power.py`: `required_n_paired(p_discordant, delta, *, alpha, power)`
- `clusters=` on `paired_bootstrap` and `test_clusters=` on `corrected_pass_rate`

## The idea, simply

Ten questions about the same document are not ten independent facts: if the model misreads the
document, all ten go wrong together. Treating them as independent makes the error bars too narrow.
So we either add up the errors within each cluster before computing the variance, or resample
whole clusters in the bootstrap.

For planning, the number of paired examples needed to detect a difference Δ is
`(z₁₋α/₂ + z_power)² · (p_disc − Δ²) / Δ²`.

## How I know it's right

- With one item per cluster the clustered SE equals the ordinary SE (`std / √n`).
- Duplicating items into clusters makes the SE larger.
- `required_n_paired(0.2, 0.05)` = 621: `(1.95996 + 0.84162)² = 7.8489`, times `(0.2 − 0.0025) / 0.0025 = 79`,
  gives 620.06, rounded up.
- Not run yet: tests are written but the maintainer runs them.

## What surprised me / gotchas

- `z_{power}` is a one-sided quantile (0.8416 for 80% power), not the two-sided value (1.2816).
  Using the two-sided helper by mistake gives about 831 instead of 621.
- No small-sample correction factor is applied, so singleton clusters match the ordinary SE exactly.

## How AI helped (and where it was wrong)

_To be filled in by the author._

## Learn more

- Miller (2024), *Adding Error Bars to Evals* (arXiv 2411.00640).
- Liang & Zeger (1986), *Longitudinal data analysis using generalized linear models*.
- Architecture §13.5 and §13.6.