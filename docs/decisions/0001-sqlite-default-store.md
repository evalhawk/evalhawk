# ADR-0001: SQLite is the default store

- **Status:** Accepted
- **Date:** 2026-09-27
- **Deciders:** EVSGoud

## Context

evalhawk stores its own evaluation state: examples, traces, verdicts, human labels, split
assignments and run manifests. The user's source data stays where it is.

Constraints:

- It runs on a laptop with no server to install.
- The CLI and the labeling UI may use the same data **at the same time**.
- Split assignments must be **impossible to change** once written, enforced by the storage
  itself and not just by application code (see [ADR-0006](0006-content-addressed-ids-and-splits.md)).
- Lean dependencies: the core install should not pull in a database driver or an ORM.
- Users upgrade evalhawk while keeping old databases, so the schema must migrate safely.

## Decision

The default `Store` implementation is **SQLite through Python's standard-library `sqlite3`**,
configured as follows:

- `PRAGMA journal_mode = WAL`: many readers and one writer at the same time (CLI plus UI).
- `PRAGMA busy_timeout = 5000` on every connection: a writer waits instead of failing with
  "database is locked".
- `PRAGMA foreign_keys = ON` on every connection (SQLite has it off by default).
- `BEFORE UPDATE` and `BEFORE DELETE` triggers on `splits` that `RAISE(ABORT)`.
- Schema version kept in `PRAGMA user_version`; migrations are numbered SQL files, applied
  **forward only**, each in one transaction.
- Default location: `.evalhawk/eval.db` in the project directory (git-ignored).

All access goes through the `Store` protocol, so other backends can be added later
without touching `core/`, `stats/` or `services/`.

## Consequences

**Positive**

- Zero install: `sqlite3` ships with Python on every OS we support.
- Transactions, constraints and triggers give real integrity guarantees (immutable splits,
  idempotent verdicts through a composite primary key).
- One file that users can copy, back up or attach to a bug report.

**Negative**

- Only one writer at a time. That's fine for one person or a small team on one machine, but
  not for many machines writing at once. A Postgres store is a "Later" roadmap item.
- WAL mode is unreliable on network drives and cloud-synced folders (OneDrive, Dropbox). The
  docs must say: keep `.evalhawk/` on a local disk.
- We write SQL by hand, so schema changes need care and migration tests.

## Alternatives considered

| Option | Why not |
|---|---|
| DuckDB | Excellent for analytics, but it's an extra dependency, has no triggers, and allows only one process with write access |
| PostgreSQL | Needs a server; wrong default for a laptop-first tool. Possible later through the `Store` protocol |
| JSONL files | No transactions, no constraints, no safe concurrent writes |
| SQLAlchemy / an ORM | A heavy dependency for a small, stable schema; hides the pragmas and triggers we rely on |

## References

- SQLite WAL mode: <https://www.sqlite.org/wal.html>
- `docs/architecture.md`, section 4.2 (schema)
