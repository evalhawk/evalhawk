# ADR-0009: Lean runtime: NumPy and the standard library, no SciPy

- **Status:** Proposed (awaiting approval by both maintainers)
- **Date:** 2026-09-29
- **Deciders:** Venkata Sai Karthik, Krishna Nandimandalam

## Context

The priorities for users are low latency, accuracy and dependability. SciPy was listed as
a core dependency for three things: the normal quantile (the "1.96" in a 95% interval),
the exact binomial test (McNemar), and later calibration fitting.

Measurements on a Windows laptop (2026-09-28, warm imports, three runs each):

| Import | Time |
|---|---|
| `numpy` | ~77 ms |
| `pydantic` | ~41 ms |
| `typer` | ~63 ms |
| `scipy.stats` | **~745 ms** |

Accuracy of standard-library replacements, checked against SciPy:

| Need | Replacement | Agreement with SciPy | Speed |
|---|---|---|---|
| Normal quantile | `statistics.NormalDist().inv_cdf` | Within 7e-16 | Instant |
| Exact McNemar p-value | Log-space tail sum using `math.lgamma` and a term-ratio recurrence (~12 lines) | Worst relative difference 2.1e-10 over 20,000 random cases; same to 10 significant digits | 10–100× faster |

A related finding: for binary data, bootstrapping **counts** (multinomial or binomial) instead
of rows gives the same distribution and was ~980× faster (0.7 ms vs 651 ms for a
Rogan-Gladen interval with 2,000 resamples).

## Decision

- Runtime dependencies are **NumPy, Pydantic and Typer**. SciPy is removed from
  `dependencies`.
- SciPy moves to the **`dev` dependency group** and is used only in tests, as a reference
  implementation our functions must match.
- `stats/` uses NumPy and the standard library only. Calibration fitting (Platt, isotonic)
  is implemented in NumPy when it's needed (Phase 6).
- Bootstraps over binary data resample counts, not rows, wherever the statistic allows it.

## Consequences

**Positive**

- Every CLI command starts about 0.75 s faster.
- A smaller install for users.
- SciPy still guards correctness, through tests.

**Negative**

- We maintain a few numerical routines ourselves, so each one needs a reference test against SciPy.
- If a later method truly needs SciPy, it goes behind an optional extra with a lazy import.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep SciPy as a core dependency | ~0.75 s added to every command; a large install for three small functions |
| Lazy-import SciPy only where used | Still a large install; latency moves to the first `report` call instead of disappearing |

## References

- Benchmarks run on 2026-09-28 (scripts kept in the session scratchpad; to be added to `experiments/benchmarks/` with S4)
- Python `statistics.NormalDist`: <https://docs.python.org/3/library/statistics.html#statistics.NormalDist>
