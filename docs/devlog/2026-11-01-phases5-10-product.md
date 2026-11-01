# Phases 5-10 · From library to product

- **Author:** Venkata Sai Karthik
- **Date:** 2026-11-01
- **Card:** [Phases 5-10](../development/workplan.md) · **PR:** #30, #31, #32, #33, #34, #35

## What I built

The parts that turn the statistics engine into a tool people can use:

| Phase | What | Entry point |
|---|---|---|
| 5 | Local web app: runs dashboard, blind labelling, judge report cards | `evalhawk ui` |
| 6 | Cheap-then-strong judge cascades and the risk-coverage curve | `type = "cascade"`, `evalhawk judges cascade` |
| 7 | Bias-corrected paired comparison and a CI gate (plus a GitHub Action) | `compare --corrected`, `evalhawk gate` |
| 8 | RAG retrieval metrics with cluster-bootstrap intervals | `evalhawk retrieval` |
| 9 | Failure discovery: cluster why answers failed | `evalhawk discover` |
| 10 | README with real output, an offline RAG example, a release workflow | `examples/rag-support` |

## The idea, simply

**Cascades.** Ask the cheap judge first. If it is very sure (say p ≥ 0.9 or p ≤ 0.1), keep its
answer; otherwise ask the expensive one. The risk-coverage curve shows, for each threshold,
how many answers the cheap judge handles and how often it is wrong on those.

**Corrected comparison.** If the judge catches only part of the real difference, it shrinks
the gap between versions. The shrink factor is Youden's J = sensitivity + specificity − 1, so
the true difference ≈ judged difference / J. Dividing also stretches the interval, which is
why a correction can turn "slightly better" into "inconclusive": it removes bias, it cannot add
information.

**Retrieval metrics.** hit@k asks "did any relevant document make the top k?", recall@k asks
"what share of the relevant ones did?", MRR rewards finding the first one early, and nDCG@k
rewards good ordering. Each gets a bootstrap interval, because 9 queries say very little.

**Failure discovery.** Turn each failure reason into word weights (TF-IDF: rare words count
more), then group similar reasons (k-means). Each group is a candidate new criterion; a human
decides.

## How I know it's right

- The corrected paired difference covers the truth 92-98% of the time in a slow simulation
  (`tests/validation/test_paired_correction_coverage.py`).
- Cascade predictions match the curve exactly at every threshold; retrieval metrics match
  hand-computed values; clustering recovers three planted themes and is seed-reproducible.
- The shipped examples run end to end in tests (`tests/integration/test_examples.py`), so the
  numbers in the README cannot silently drift.

## What surprised me / gotchas

- I expected the corrected comparison to turn the demo's "inconclusive" into "better". It did
  not (+5.3 points, interval −5.1 to +15.9), and that is the correct answer.
- A budget check placed *before* acquiring the concurrency semaphore let every queued call
  through; it has to be checked after.
- Rich fixes its console width at import, so table tests need a pinned width.
- `setup-uv` has no floating major tag; pin the full version.
- Plain TF-IDF was enough for failure reasons (short, keyword-heavy), so no embedding model
  or scikit-learn was needed.

## How AI helped (and where it was wrong)

Claude Code wrote most of the code and tests from the design docs, with me reviewing each
phase. It got several test expectations wrong at first (PII count, an undefined lift reported as
0, a test that was vacuous behind an `if`) and broke files twice by writing escaped newlines
through shell heredocs; all were caught by the test suite or the type checker.

## Learn more

- Geifman and El-Yaniv, *Selective Classification for Deep Neural Networks* (2017): risk-coverage.
- Rogan and Gladen, *Estimating prevalence from the results of a screening test* (1978).
- Järvelin and Kekäläinen, *Cumulated gain-based evaluation of IR techniques* (2002): nDCG.
- Shankar et al., *Who Validates the Validators?* (2024): criteria drift and error analysis.
