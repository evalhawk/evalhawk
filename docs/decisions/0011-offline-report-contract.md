# ADR-0011: Make offline report assumptions explicit

- **Status:** Proposed
- **Date:** 2026-10-11
- **Deciders:** EVSGoud, kclectic0501

## Context

Stage D connects immutable stored outcomes to existing statistical routines.
Labels can disagree; repeats and paraphrases are dependent. Existing PPI,
calibration and agreement intervals assume independent observations.

## Decision

- Reserve train for tuning; dev supplies human calibration; test supplies judge
  predictions. Log every test read, including per-tag and comparison reads.
- For each annotator use their latest timestamp. Equal-time conflicting answers
  are unresolved. Ignore UNKNOWN votes; majority wins; ties/no votes are excluded
  and counted. Require inclusion probability 1 until weighted inference exists.
- Rate reports select the lexicographically smallest example ID and repeat 0
  per locked group (or example without a group), before inspecting outcomes.
  This estimates the **fixed representative population**, not all paraphrases.
  Group IDs must identify independent cases; independence cannot be inferred.
- Report judge UNKNOWN and missing/unresolved calibration separately. Corrected
  results are conditional on known judgments and resolved labels. Representative
  sampling, label missingness, and stable error rates are explicit assumptions.
- Pair comparisons by example and repeat. Their difference measures the judge
  proxy, not bias-corrected human quality. Use group-aware bootstrap intervals;
  only independent pairs receive McNemar and IID sample planning. Planning uses
  an explicit target effect, never the observed insignificant difference.
- Stream scalar outcomes through the Store. Use growable byte buffers for
  outcomes and integer cluster codes; arrays, ID maps and bootstrap workspace
  remain O(n). Adaptive bootstrap batching targets 32 MiB temporary workspace,
  not total process memory, with one resample as the minimum batch.
- Imports validate one bounded batch before persisting it. Earlier batches may
  survive later errors; reimport using the persisted run manifest is idempotent.
  A target version is not a run identity. No network or answer-key access occurs
  during inference.
- Schema 2 adds virtual scalar projections of JSON records without duplicating
  their source of truth; migrations are transactional and forward-only.

## Consequences

**Positive**

- A working, reproducible offline path with auditable denominators and assumptions.
- No false claim that IID calibration intervals handle dependent paraphrases.

**Negative**

- Representative reports discard other paraphrases and may lose precision.
- Full-population clustered PPI/calibration, weighted sampling, and globally
  atomic imports remain follow-ups. Labels whose identical payload reappears
  at a later time retain their original content ID/timestamp; use a distinct note
  to record a new event until an annotation-event identity ADR is accepted.
- Tag metadata can change while split/group assignments remain locked.

## Alternatives considered

| Option | Why not |
|---|---|
| Treat all rows as independent | Understates uncertainty for grouped inputs |
| Rewrite all statistical estimators now | Requires separately validated clustered estimators |
| Keep full JSON joined records | Retains needless text and Python validation overhead |

## References

- [Architecture](../architecture.md)
- [ADR-0010](0010-data-backbone-contracts.md)
- [SQLite generated columns](https://www.sqlite.org/gencol.html)