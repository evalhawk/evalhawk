# S2 · Judge agreement

- **Author:** Krishna Nandimandalam
- **Date:** 2026-10-09
- **Card:** [#6](../development/workplan.md) · **PR:** #TBD

## What I built

`Confusion` dataclass and four functions for agreement metrics:
- `confusion(human, judge) -> Confusion`: 2×2 confusion matrix
- `sensitivity(c) -> Estimate`: TP / (TP + FN) via Wilson interval
- `specificity(c) -> Estimate`: TN / (TN + FP) via Wilson interval
- `cohen_kappa(human, judge, rng) -> Estimate`: agreement beyond chance via percentile bootstrap

Plus private validation helpers in `_checks.py`: `as_binary`, `check_same_length`, `check_n_boot`.

## The idea, simply

Treat humans as ground truth; PASS is the positive class. A naive "always PASS" judge gets high
accuracy but 0 specificity, so we report sensitivity and specificity separately. Cohen's kappa
removes chance agreement: κ = (p_o − p_e) / (1 − p_e). The formula:
- p_o = (TP + TN) / n (observed agreement)
- p_e = P(human=PASS)·P(judge=PASS) + P(human=FAIL)·P(judge=FAIL)

Kappa = 1 means perfect agreement, 0 means random, negative means worse than random.

## How I know it's right

- Hand example: human [1,1,1,1,1,1,0,0,0,0], judge [1,1,1,1,1,0,1,0,0,0] yields
  tp=5, fn=1, fp=1, tn=3; sensitivity 5/6 ≈ 0.8333; specificity 3/4 = 0.75;
  p_o=0.8, p_e=0.52, κ ≈ 0.5833. ✓
- Always-PASS judge has specificity point 0.0. ✓
- Error cases: length mismatch, invalid values, empty arrays, 2-D arrays, no PASS/FAIL, n_boot < 100. ✓
- Kappa properties: perfect judge → κ = 1.0; interval within [-1, 1]; order-independent. ✓
- Reproducible: same seed → identical results. ✓

## What surprised me / gotchas

- The `as_binary` helper must accept bool and convert to int; tricky dtype detection required.
- Degenerate resamples (p_e ≥ 1) must be dropped per P3; if > 1% dropped, raise ValueError.
- Confusion dataclass uses `frozen=True` with slots for immutability and efficiency.
- The percentile interval (P2) uses `np.quantile(..., [(1−c)/2, (1+c)/2])` for both bounds.

## How AI helped (and where it was wrong)

Asked for bootstrap implementation and array validation. Had to clarify:
- Multinomial resampling of counts (not examples) for kappa.
- Degenerate rate check (> 1%) and error message.
- `as_binary` dtype logic for int/float/bool arrays.

## Learn more

- Cohen, J. (1960). "A coefficient of agreement for nominal scales." Educational and Psychological Measurement.
- Architecture §13.1: naming convention trap (human=truth, PASS=positive).
