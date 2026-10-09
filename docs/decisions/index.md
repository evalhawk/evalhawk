# Architecture Decision Records

An **ADR** is a short document that records one important decision: the context, what we
chose, what it costs us, and what we rejected. Think of it as the project's memory. Six
months from now, "why is it like this?" has a written answer instead of a guess.

## When to write one

Write an ADR when a decision is **hard to undo** (a "one-way door") or when the two
maintainers disagreed and settled it. Examples: storage format, ID and hashing schemes,
public API shape, a new core dependency, a change to the statistics contract.

Do **not** write one for easily reversible choices (CLI colours, internal helper names).

## How

1. Copy [the template](0000-template.md) to `NNNN-short-title.md` with the next number.
2. Open a pull request with status **Proposed**. Discuss in the PR.
3. On merge, set the status to **Accepted**.
4. ADRs are never edited after acceptance, except for their status. To change a
   decision, write a new ADR and mark the old one **Superseded by ADR-NNNN**.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-sqlite-default-store.md) | SQLite is the default store | Accepted |
| [0002](0002-thin-edges-thick-core.md) | Thin edges, thick core | Accepted |
| [0003](0003-binary-criteria-only.md) | Binary criteria only | Accepted |
| [0004](0004-protocols-and-helper-base-classes.md) | Protocols are the contract; helper base classes are optional | Accepted |
| [0005](0005-package-layout.md) | Package layout and enforced layer rules | Accepted |
| [0006](0006-content-addressed-ids-and-splits.md) | Content-addressed IDs and immutable hash-based splits | Accepted |
| [0007](0007-build-order.md) | Build the statistics core and storage as parallel tracks | Accepted |
| [0008](0008-zensical-docs.md) | Zensical for the documentation site | Accepted |
| [0009](0009-lean-runtime-no-scipy.md) | Lean runtime: NumPy and the standard library, no SciPy | Accepted |
