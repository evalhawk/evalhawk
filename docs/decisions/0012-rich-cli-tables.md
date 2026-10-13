# ADR-0012: Use Rich for CLI tables

- **Status:** Proposed
- **Date:** 2026-10-11
- **Deciders:** EVSGoud, kclectic0501

## Context

The offline demonstration needs readable tables containing estimates, intervals,
denominators and warnings. Typer already installs Rich transitively: locally
Typer 0.27.2 requires `rich>=13.8.0`, and Rich 15.0.0 is installed.

## Decision

Declare `rich>=13.8.0` directly because application code imports it. Use Rich
only at the CLI boundary, with markup disabled for user-controlled text.
Keep services, statistics and stores independent of terminal presentation.
Implementation is authorized by the pairing session; acceptance still requires
both maintainers' review. No accepted ADR is rewritten.

## Consequences

**Positive**

- Readable cross-platform tables without maintaining terminal escape handling.
- No new dependency family relative to the installed Typer dependency graph.

**Negative**

- CLI presentation depends explicitly on Rich and needs captured-output tests.

## Alternatives considered

| Option | Why not |
|---|---|
| Hand-built tables | More wrapping and terminal-width code to maintain |
| Implicit transitive dependency | Direct imports should declare their dependencies |

## References

- [Rich package metadata](https://pypi.org/pypi/rich/json): 15.0.0,
  Python >=3.9, MIT, verified during implementation.
- [Typer dependencies](https://github.com/fastapi/typer/blob/master/pyproject.toml)