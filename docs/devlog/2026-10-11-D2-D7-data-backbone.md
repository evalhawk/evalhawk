# D2-D7 · Data backbone

- **Authors:** Krishna Nandimandalam and Venkata Sai Karthik (paired session)
- **Date:** 2026-10-11
- **Cards:** [D2-D7](../development/workplan.md) · **PR:** pending
- **Status:** implementation ready for human review; ADR approval and CI pending

## What I built

Domain records, deterministic split sets, structural protocols, a synchronous SQLite
store, streaming JSONL/CSV sources, and independent in-memory and model fakes.
`Store.paired_records(...)` exposes explicit judge/human rows; it does not run estimators.

## The idea, simply

Related examples share a `group_id`, so the split lottery uses their common key. Tags are
separate labels such as billing or safety: they support filtered counts without deciding
which pile an example enters. Each split set freezes its assignment and grouping snapshot.
Changing today's metadata must not rewrite yesterday's evaluation history.

SQLite and the in-memory fake implement the same protocol without sharing an implementation.
Shared tests therefore check the contract twice instead of merely testing the fake against itself.

## How I know it's right

- Golden IDs, normalized-text equivalence, JSON round trips, and Hypothesis split repeatability.
- Shared store tests for immutable assignments, atomic batches, annotation history, UNKNOWN,
  verdict cache conflicts, duplicate tags, and grouping snapshots.
- SQLite trigger, audit, WAL reader, schema-version, and open-error checks.
- Streaming 100,000-row source checks and an uninstrumented 20,000-insert timing check.
- Full pytest, strict typing, lint, import boundaries, strict docs build, and wheel inspection.
- Coverage measured without slow timing benchmarks: 93% overall before final regression additions;
  core and stats satisfy the 90% target.

## What surprised me / gotchas

- Pydantic defaults need validation to keep identity stable through JSON round trips.
- A run's timestamp distinguishes executions; resume must retain the original run record.
- Repeated outputs need a repeat index. Trace identity also includes retrieved contexts.
- Frozen Pydantic attributes do not make nested JSON deeply immutable; stores revalidate records.
- Accepted ADRs are historical records, not editable design drafts. The changes are in
  [Proposed ADR-0010](../decisions/0010-data-backbone-contracts.md), awaiting both maintainers.
- Per-row tag deletion reduced timing margin; bounded batch deletion retains atomicity.
- Coverage instrumentation distorts wall-clock benchmarks, so timing is checked separately.
- The OneDrive virtualenv caused access errors. Validation used an external uv environment
  with copy-mode installs; no runtime dependencies were added.

## How AI helped (and where it was wrong)

GitHub Copilot drafted code, tests, documentation, and local verification commands after
the maintainers agreed on the contracts. Human review, line-by-line understanding, and CI
approval remain pending; tool success does not substitute for those checks.

Earlier explanations overstated several guarantees: a new salt does not erase test exposure,
tags do not enforce independence, hash splitting only approximates tag balance, and NFC/LF
normalization is not universally appropriate for byte-exact tasks. ADR-0010 records the limits.

## Review And PR Checklist

Suggested PR title: `feat(core): implement D2-D7 data backbone`.

- **What changed:** models, grouped split contracts, sync store, streaming sources, fakes,
  shared tests, and proposed identity/storage decisions. Statistics implementations are unchanged.
- **What I learned:** distinguish dependence groups from topic tags; freeze history rather
  than current metadata; validate serialization before trusting a content ID.
- **How AI was used:** implementation and test drafting, explanations, and verification;
  both maintainers review all generated work before committing.
- **Review focus:** identity goldens, shallow immutability, split snapshots, source schema,
  SQLite migration packaging, and audit boundaries. This spans the paired core/storage track.
- **Remaining work:** X1-X3 Store-to-stats/CLI integration, label adjudication and UNKNOWN policy,
  calibration lifecycle, dataset registration, exact stratification, and byte-exact input support.
- **Before merge:** both maintainers approve ADR-0010 and the PR; CI passes. No commit or push
  is part of this implementation session.

## Learn more

- [Data backbone contracts](../decisions/0010-data-backbone-contracts.md)
- [Engineering standards](../development/standards.md)
- [Architecture](../architecture.md)