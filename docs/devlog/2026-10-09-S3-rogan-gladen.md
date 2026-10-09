# S3 · Rogan-Gladen correction

- **Author:** Krishna Nandimandalam
- **Date:** 2026-10-09
- **Card:** [#7](../development/workplan.md) · **PR:** #TBD

## What I built

In `stats/correction.py`:
- `rogan_gladen(q, sensitivity, specificity) -> float`: `(q + c − 1) / (s + c − 1)`, clipped to [0, 1]
- `corrected_pass_rate(judge_test, judge_cal, human_cal, *, rng, n_boot=2000, confidence=0.95, test_clusters=None) -> Estimate`
- `MIN_YOUDEN = 0.1`, and `JudgeTooWeakError` in `core/errors.py`

## The idea, simply

If a judge passes 95% of good answers but also 40% of bad ones, its raw pass rate is inflated.
The measured rate is `q = s·θ + (1−c)(1−θ)`, so we solve for the true rate θ. The denominator
`s + c − 1` (Youden's J) says how much better than a coin flip the judge is; when it is close to
zero the correction blows up, so we refuse instead of reporting a number.

The error bar has two sources, the calibration set (which gives s and c) and the test set
(which gives q), so each is resampled independently.

## How I know it's right

- `rogan_gladen(0.82, 0.95, 0.60)` is 0.42 / 0.55 ≈ 0.7636.
- Clipping, a perfect judge (θ = q) and the refusal at J ≤ 0.1 are tested.
- A large simulated world recovers the true rate inside its interval.
- A `slow` benchmark checks 2,000 resamples on 100k test items run in under 50 ms.
- Not run yet: tests are written but the maintainer runs them.

## What surprised me / gotchas

- Bootstrapping counts (`rng.multinomial`, `rng.binomial`) is vectorised, which is what makes the
  50 ms target realistic; a Python loop over resamples is far slower.
- Resamples where a class is missing or J ≤ 0 are dropped; more than 1% dropped means the interval
  would be unreliable, so we raise.
- `test_clusters` resamples whole clusters of the test set (shared helper in `stats/clustered.py`).

## How AI helped (and where it was wrong)

_To be filled in by the author._

## Learn more

- Rogan & Gladen (1978), *Estimating prevalence from the results of a screening test*.
- *How to Correctly Report LLM-as-a-Judge Evaluations* (arXiv 2511.21140).
- Architecture §13.3.