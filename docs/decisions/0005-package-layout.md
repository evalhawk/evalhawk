# ADR-0005: Package layout and enforced layer rules

- **Status:** Accepted
- **Date:** 2026-09-27
- **Deciders:** EVSGoud

## Context

The first design (architecture.md, earlier version) had an `analysis/` package for use
cases, no home for built-in targets, a `rag/` package mixing math and prompts, and a
dependency rule that existed only as prose. Two people will now work on the codebase in
parallel, so the boundaries must be obvious and enforced by tooling, not memory.

## Decision

**Layout.** `src/` layout. One top-level package per layer or adapter family:

| Package | Layer | Contents |
|---|---|---|
| `core/` | Domain | Models, protocols, IDs, splits, result value objects, errors |
| `stats/` | Domain | Pure functions over NumPy arrays (including retrieval metrics) |
| `services/` | Application | Use cases, one module per user action (`evaluate`, `calibrate`, `estimate`, `compare`, `label_queue`, `export`) |
| `runner/` | Application | Async execution engine: concurrency, retries, budget, cache lookups |
| `judges/`, `targets/`, `sources/`, `storage/` | Adapters | Implementations of the ports |
| `config.py`, `plugins.py`, `wiring.py` | Composition | TOML to typed config, entry-point registry, and the **composition root** that builds all objects |
| `testing/` | Public support | `FakeJudge`, `FakeTarget`, `InMemoryStore` for users and for our own tests |
| `cli/`, `ui/` | Interfaces | Parse input, call services, render output |
| `clustering/` | Optional feature | Behind the `[cluster]` extra |

Specific choices:

- `analysis/` is renamed **`services/`**, because "analysis" was easily confused with `stats/`.
- **`targets/`** is added for `CallableTarget`, `HttpTarget`, `OpenAICompatibleTarget` and
  `RecordedTarget`.
- **`wiring.py`** is the only module that constructs concrete adapters. It is deliberately
  not called `bootstrap.py`, to avoid confusion with the statistical bootstrap.
- **`rag/` is dissolved**: retrieval metrics go to `stats/retrieval.py`, and RAG prompt
  templates to `judges/templates/rag/`.
- **No `utils.py` or `helpers.py` modules.** Every function belongs to a layer.
- A package is created **in the phase that first needs it**, never ahead of time.

**Dependency rule (arrows point inward):**

```
cli, ui ──► wiring ──► services ──► runner ──► core, stats
                  └──► judges, targets, sources, storage ──► core (and stats)
```

**Enforcement.** `import-linter` (dev-only) checks these contracts in pre-commit and CI:

1. `core` and `stats` import nothing from any other evalhawk package, nor `typer` or `sqlite3`.
2. `services` and `runner` never import concrete adapters, `wiring`, `cli` or `ui`.
3. Adapters never import `services`, `runner`, `wiring`, `cli` or `ui`.

Contracts 2 and 3 are written in `pyproject.toml` but commented out, because
`import-linter` requires the source packages to exist. They are switched on in the phase
that creates those packages.

## Consequences

**Positive**

- New contributors can find any code from the name of the thing they want.
- Layer violations fail in CI with a precise message, not in code review months later.
- The two maintainers can work in parallel on different layers, with protocols as the
  contract between them.

**Negative**

- More top-level packages than a flat layout.
- `import-linter` is one more dev dependency and one more config block to maintain.

## Alternatives considered

| Option | Why not |
|---|---|
| Group by feature (`rag/`, `cascade/`, ...) | Features cut across layers; the dependency rule becomes unenforceable |
| An `adapters/` parent folder | Longer import paths for the classes users touch most (`evalhawk.judges.OpenAICompatibleJudge`) |
| Rules in docs only | They erode silently |

## References

- import-linter: <https://import-linter.readthedocs.io/>
- `docs/design/patterns.md`
