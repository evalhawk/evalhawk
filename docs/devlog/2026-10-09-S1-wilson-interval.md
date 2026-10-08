# S1 · Wilson score interval

- **Author:** Krishna Nandimandalam
- **Date:** 2026-10-09
- **Card:** [#5 S1](../development/workplan.md) · **PR:** TBD

## What I built

A Wilson score confidence interval for binomial proportions: `wilson_interval(k, n, *, confidence=0.95) → Estimate`.
Also created private helpers in `src/evalhawk/stats/_checks.py` for validation: `check_confidence`, `z_value`.

Main signature:
```python
def wilson_interval(k: int, n: int, *, confidence: float = 0.95) -> Estimate:
    """Compute a Wilson score confidence interval for a proportion."""
```

## The idea, simply

The Wald interval (`p̂ ± z·√(p̂(1−p̂)/n)`) has a famous bug: when you observe 0 successes in 10 trials, it gives [0, 0]—false
certainty that the true rate is exactly 0. It can also leave [0, 1], claiming the parameter isn't bounded.

Wilson's fix (1927) pulls the centre of the interval toward 0.5, making it narrower when the data is sparse. The formula involves a
z-score based on the confidence level and some algebraic rearrangement. The result is **guaranteed to stay in [0, 1]** and is more accurate
for all proportions and sample sizes.

## How I know it's right

- **Golden values**: Four reference cases (82/100, 0/10, 10/10, 500/1000) match published tables to 5 decimals.
- **Property tests** (Hypothesis, 200+ cases per property):
  - Bounds always satisfy 0 ≤ low ≤ high ≤ 1.
  - Symmetry: the interval for k successes mirrors the interval for (n−k) successes.
  - Narrowing: doubling sample size consistently narrows the interval.
- **Error cases**: TypeError rejects bools, ValueError rejects floats, out-of-range k, bad confidence (0 or 1 or negative).
- **Metadata**: method="wilson", n matches input, confidence and unknown_rate defaults are correct.
- **String format**: matches the spec exactly: `"0.820 [0.733, 0.883] (wilson, n=100, unknown=0.0%)"`.

## What surprised me / gotchas

1. **Bool rejection comes first.** Python treats `True` as 1 (it's a subclass of `int`), so I had to check `isinstance(k, bool)`
   before other int checks. Tests verify the error message names "bool", not just "not int".

2. **Float noise at bounds.** The formula can produce slightly negative low or slightly-over-1 high due to floating-point rounding.
   I clamp with `max(0.0, ...)` and `min(1.0, ...)`, knowing Estimate's post-init will never fail because the values are within [0, 1].

3. **Symmetry property is delicate.** Testing `low(k) ≈ 1 - high(n−k)` requires using `pytest.approx` with a loose tolerance
   (1e-10 at the float64 level). The property holds exactly in theory but not in floating-point practice.

4. **Confidence-level computation.** The z-score is computed via `statistics.NormalDist().inv_cdf((1 + confidence) / 2)`, which is
   the inverse CDF of the standard normal at the cumulative probability. For confidence=0.95, this gives z ≈ 1.96. I verified
   this against standard tables.

## How AI helped (and where it was wrong)

*Left for the maintainer to fill in.*

## Learn more

- Wilson, E. B. (1927). "Probable inference, the law of succession, and statistical inference." *Journal of the American
  Statistical Association*, 22(158), 209–212.
- Brown, L. D., Cai, T. T., & DasGupta, A. (2001). "Interval estimation for a binomial proportion." *Statistical Science*, 16(2),
  101–133.
- Card [#5 S1](../development/workplan.md) in workplan
- Standards §5: [Pure functions in stats/](../development/standards.md)
- Architecture §7: [Statistics core](../architecture.md)
