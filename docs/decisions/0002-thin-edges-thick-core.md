# ADR-0002: Thin edges, thick core

- **Status:** Accepted
- **Date:** 2026-09-27
- **Deciders:** EVSGoud

## Context

evalhawk's value is that its numbers can be trusted. Users bring very different setups:
OpenAI, Ollama, JEV or in-house judges; Python apps, HTTP APIs or pre-recorded outputs;
JSONL, CSV, Langfuse or OpenTelemetry traces.

If every part were pluggable, a user could swap in a broken estimator or skip blind
labeling, and the numbers would no longer mean anything. If nothing were pluggable,
nobody could use the tool with their own stack.

## Decision

Split the system into two zones:

| Pluggable edges (thin) | Fixed core (thick) |
|---|---|
| Target (the user's app), judge, trace source, embedder, store backend | Statistical estimators and intervals, split assignment and locking, blind labeling, reporting rules |

- Edges are **ports and adapters**: each port is a `typing.Protocol` in `core/protocols.py`,
  and adapters implement it.
- The core is **not** configurable in ways that could break its guarantees. Users choose
  *where numbers come from*, never *how they are computed*.
- Where the core offers choices (Rogan-Gladen vs PPI, queue strategies), every option is one
  **we** implement and validate. There's no user-supplied estimator.

## Consequences

**Positive**

- One guarantee holds for every user: the reported interval was computed by validated code.
- Adding an integration is additive: a new adapter file, no change to the core.
- The core can be tested without any network, vendor SDK or database.

**Negative**

- Users can't plug in their own statistics. That's deliberate, but some advanced users may
  want it; we accept that.
- Every new estimator we add must pass the full validation suite (coverage simulation plus
  the `ppi-python` oracle) before it ships.

## Alternatives considered

| Option | Why not |
|---|---|
| Everything pluggable (framework style) | Can't guarantee anything about the output |
| Monolith with built-in vendor integrations | Vendor API changes break the core; heavy dependencies |

## References

- `docs/architecture.md`, sections 3.1 and 3.2
- Hexagonal architecture (ports and adapters), Alistair Cockburn
