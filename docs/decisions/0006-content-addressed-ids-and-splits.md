# ADR-0006: Content-addressed IDs and immutable hash-based splits

- **Status:** Accepted
- **Date:** 2026-09-27
- **Deciders:** EVSGoud

## Context

Three guarantees depend on how things are identified:

1. **Idempotency and caching.** Re-importing the same data must not create duplicates, and
   a judge must never be paid twice for the same judgment.
2. **Reproducibility.** The same data, config and seed must give the same report on any
   machine.
3. **No test-set leakage.** An example must stay in the same split (train, dev or test)
   forever, across every run and every machine. Otherwise, tuning on dev silently leaks
   into test.

These are **one-way doors**. Once users have databases, changing the scheme orphans every
stored verdict and label, and moves examples between splits.

## Decision

**IDs are content hashes.**

- `content_id(obj)` = lowercase hex SHA-256 of the object's **canonical JSON**: UTF-8,
  sorted keys, separators `(",", ":")`, no NaN or Infinity.
- `example_id` hashes the example's input (and reference, if present). `trace_id` hashes
  `(example_id, run_id, output)`.
- `judge_id` hashes `(adapter type, model, template text, template version, sampling
  parameters, few-shot example IDs)`. Template text is normalised to **LF line endings**
  before hashing, so the same template gives the same ID on Windows and Linux.
- A wrapper that changes a judge's **answers** (recalibration, cascades, strictness) gets a
  new `judge_id` derived from the inner ID. A wrapper that changes only **how** answers are
  obtained (caching, timing, retries) keeps the inner `judge_id`.

**Splits are hash-based and immutable.**

- `key = group_id if set else example_id`
- `u = int(sha256(salt + key)[:8], 16) / 16**8`, mapped onto the cumulative ratios
  (default train 0.2, dev 0.4, test 0.4).
- Once written, a split row can never change: SQLite triggers abort any `UPDATE` or
  `DELETE` ([ADR-0001](0001-sqlite-default-store.md)). Changing the `salt` creates a brand-new
  split set; it never edits the old one.
- Every read of the test split is logged in `test_access_log`.

**Freezing.** Golden tests pin the exact output of `content_id`, `judge_id` and
`assign_split` for fixed inputs. Changing any of them is a breaking change: a new major
version, a CHANGELOG entry, and a migration.

## Consequences

**Positive**

- Duplicates are impossible by construction, and the verdict primary key
  `(trace_id, criterion_id, judge_id)` doubles as the judge cache.
- A crashed run resumes with zero repeated API calls.
- Splits agree across machines and runs with no coordination.

**Negative**

- Any mistake in canonicalisation is permanent once released, hence the golden tests.
- Two semantically equal inputs that differ in formatting (for example, extra whitespace)
  get different IDs. We accept that rather than guess at normalisation of user data.
- Hash-based split ratios are only approximately exact for small datasets.

## Alternatives considered

| Option | Why not |
|---|---|
| Auto-increment or UUID IDs | Re-imports create duplicates; caching and pairing across runs break |
| Random splits with a seed | The assignment changes when the dataset changes; examples jump between splits |
| Mutable splits with an audit log | Makes leakage *visible* but not *impossible* |

## References

- `docs/architecture.md`, sections 4 and 13.11
