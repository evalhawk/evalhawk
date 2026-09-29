# ADR-0007: Build the statistics core and storage as parallel tracks

- **Status:** Proposed (awaiting approval by both maintainers)
- **Date:** 2026-09-27, revised 2026-09-29 for two maintainers
- **Deciders:** Venkata Sai Karthik, Krishna Nandimandalam

## Context

The original roadmap builds by layer: Phase 1 (models and SQLite store), then Phase 2
(statistics), then Phase 3 (judges and CLI). The statistics core is:

- the **highest-risk** part (if the math is wrong, the product is worthless);
- **independent** of everything else (it takes NumPy arrays, not models or database rows);
- the source of the first portfolio artefact (the coverage-simulation chart).

Building by layer also means nothing is usable end to end until the end of Phase 3.

## Decision

With two maintainers, **build Stage B (statistics) and Stage C (data backbone) in parallel**, one owner
per track, after a small shared contract (`Estimate`, errors) built together. This is possible because
`stats/` takes NumPy arrays and never depends on models or storage. Details and task cards are in the
[work plan](../development/workplan.md).

The stage order below still applies from Stage D onwards. Reorder the work into **stages**, each ending in something a person can use:

| Stage | Name | Usable result | Roadmap phase |
|---|---|---|---|
| A | Foundation | Green CI | 0 |
| B | Calculator | `evalhawk.stats` gives a corrected pass rate with a CI from arrays | 2 |
| C | Memory | Models, IDs, splits, SQLite store, JSONL/CSV import | 1 |
| D | Offline report | `evalhawk import` + `evalhawk report` on **pre-recorded** verdicts and labels: the first end-to-end demo, with zero LLM calls | slice of 3 |
| E | Live judge | `evalhawk eval` with judges, runner, cache, targets | rest of 3 |
| F onwards | Labeling UI, cascade study, CI gate, expansion | as in the roadmap | 4–9 |

Only `core/results.py` (the `Estimate` value object) is needed from `core/` for Stage B.

## Consequences

**Positive**

- Risk is retired first.
- The coverage chart arrives about a week earlier.
- Stage D proves the pipeline before any API cost or flakiness appears.

**Negative**

- The roadmap's phase numbers no longer match the build order, so the roadmap shows both.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep the layer order | Delays both the riskiest work and the first usable result |
