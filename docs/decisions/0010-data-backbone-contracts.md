# ADR-0010: Data backbone identities, split sets and synchronous stores

- **Status:** Proposed
- **Date:** 2026-10-11
- **Deciders:** Venkata Sai Karthik and Krishna Nandimandalam (approval pending)
- **Scope:** Replaces the identity/split details of ADR-0006 and clarifies ADR-0001
  and ADR-0004 upon acceptance. Accepted records remain unchanged until review.

## Context

An input needs a stable name, while separate executions need separate identities.
Related inputs must not straddle training and test piles. Categories used for filtering
are a different concept and may overlap. The original schema allowed only one split
per example, despite promising that a new salt creates a separate split set.

Earlier planning advice was too strong: changing a salt does not make previously
studied data unseen; exact stratification can be deterministic for a frozen dataset;
and arbitrary text normalization is not always semantics-preserving.

## Decision

### Canonical text and identity

Keep `content_id` byte-for-byte compatible: canonical JSON, sorted string keys,
fixed separators, UTF-8, no nonfinite numbers, SHA-256. `normalize_text` adds NFC
to its existing CRLF/CR-to-LF conversion. Models normalize string values recursively
in input/reference, and normalize output, contexts, group IDs and tags. Mapping keys
are not normalized. Store the normalized model data. Case, spaces and punctuation
remain significant. Metadata/config snapshots are not text-normalized.

This is an explicit text-evaluation policy, not proof that distinct byte sequences
are interchangeable in every application. Byte-exact/codepoint-sensitive evaluations
need a future explicit raw-data policy; do not silently use this normalization there.
Unicode normalization is stable for assigned characters, but newer characters require
compatible Unicode versions for cross-runtime identity guarantees.

IDs hash the following ordered JSON lists (the prefix versions each contract):

| Record | Payload after prefix |
|---|---|
| Example (`example-v1`) | input, reference |
| Run (`run-v1`) | target version, config snapshot, UTC ISO timestamp |
| Trace (`trace-v1`) | example ID, run ID, repeat index, output, contexts |
| Criterion (`criterion-v1`) | name, question, version |
| Label (`label-v1`) | trace ID, criterion ID, annotator, outcome, note, inclusion probability |
| Split set (`split-set-v1`) | salt, ratios, grouping mode |

Validate defaults before hashing and verify supplied IDs on reload. Runs retain their
original timestamp when resumed/imported; callers must persist run identity to avoid
creating a fresh run on each import. Trace repeat indices distinguish repeated outputs.
Contexts belong in trace identity because a RAG judgment depends on them.
Verdicts use the composite key `(trace_id, criterion_id, judge_id)`.

Pydantic records are frozen at the attribute level, not recursively immutable: nested
JSON containers remain mutable. Stores validate serialized IDs again and copy stored
records, so mutation of identity-bearing content is rejected at persistence boundaries.
Callers must not treat a frozen model as a recursively immutable JSON tree.

### Split sets and grouping

Group keys are `content_id(["group", group_id])`; ungrouped keys are
`content_id(["example", example_id])`. Namespaces prevent a group name from colliding
with a literal example ID. Assignment uses the first eight hex digits of
`content_id(["split-v1", salt, key])`, divided by `16**8`, against cumulative ratios.
Ratios must be finite, nonnegative and sum to one within absolute tolerance `1e-12`;
normalize by the sum for assignment. Zero-sized piles remain empty.

Each salt identifies one `(ratios, by)` configuration per store. A mismatch is an error.
Store immutable split sets and rows keyed by `(split_set_id, example_id)`, including
the split key and group snapshot. Refuse a changed grouping key in an existing set.
Metadata/tags can change; historical split/group snapshots cannot. New group members
use the same key. A new salt creates another set beside the old one, not a clean final
exam: prior exposure and tuning remain relevant, and truly fresh validation needs
previously unseen examples. Never search salts for a favorable evaluation result.

`group_id` is optional dependence metadata, not a topic: use it for paraphrases,
conversation turns or another dependence unit justified by the evaluation design.
It has one value per example. Overlapping dependence relationships need preprocessing
into connected components before the first locked assignment; adding a bridge between
already separated groups must not silently merge them.

Tags are optional overlapping report categories. They do not affect IDs or assignments.
Both identifiers must be nonempty strings, NFC, without edge whitespace/NUL. Importers
accept integer group IDs by converting to decimal strings; other non-string group IDs
are rejected. Diagnostics report actual pile/tag counts and configurable warnings for
small piles/few groups/dominant groups. Thresholds are heuristics, not statistical laws.
Exact multilabel stratification is deferred; grouped hash assignment only balances
ratios in expectation across distinct grouping keys, not necessarily across rows.

### Ports, persistence and sources

Store methods are synchronous; Judge/Target calls remain asynchronous. No runtime
dependencies are added. SQLite uses WAL, NORMAL synchronization, foreign keys,
recursive triggers, busy timeout, and transactional `user_version` migrations.
Initialize migrations under a write lock and parse SQL with `sqlite3.complete_statement`.
Enable recursive triggers to prevent REPLACE bypassing split DELETE triggers.

The schema stores validated JSON records with indexed relational keys, split sets,
tags and access logs. This reduces mapping duplication without sacrificing referential
integrity. No released SQLite schema is known in this workspace; if an existing schema
is found before merge, require a forward migration rather than treating it as version 0.

Sources stream `(Example, TargetOutput | None)`. A service, not a file source, supplies
the Run and creates Trace records. Store paired reads require a purpose; test-split
paired reads are logged. A direct cache read is not a split-scoped evaluation query:
services/runner must not use cache access to bypass audit rules.

Multiple annotations are returned explicitly; services must adjudicate/select humans
before converting rows into arrays. UNKNOWN remains stored. Calibration values use
the shared Estimate contract, but status computation belongs to services.

## Alternatives And Consequences

- Plain salt/key concatenation is ambiguous; structured JSON reuses the tested encoder.
- Topic stratification alone does not protect dependent records from crossing piles.
- Async SQLite/ORM packages add dependencies; a sync store suffices for offline work.
  Async runner integration must own a connection on its worker thread, not send a
  main-thread SQLite connection into arbitrary `asyncio.to_thread` calls.
- Typed JSON columns preserve complete records; analytic queries beyond indexed keys
  may later need explicit migrations adding columns.
- FakeJudge samples known error probabilities, not exact finite-sample rates.
- Acceptance requires both maintainers' review; do not mark ADR-0006 superseded until then.

## References

- [ADR-0001](0001-sqlite-default-store.md), [ADR-0004](0004-protocols-and-helper-base-classes.md),
  [ADR-0006](0006-content-addressed-ids-and-splits.md)
- SQLite transactions and complete statements: <https://docs.python.org/3/library/sqlite3.html>
- Unicode normalization: <https://www.unicode.org/reports/tr15/>