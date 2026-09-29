# ADR-0004: Protocols are the contract; helper base classes are optional

- **Status:** Accepted
- **Date:** 2026-09-27
- **Deciders:** EVSGoud

## Context

Users will write their own judges, targets and trace sources. We want that to take
about ten lines, without learning a class hierarchy or depending on evalhawk internals.

At the same time, writing an LLM judge well involves repetitive work: rendering a
prompt template, parsing `PASS`/`FAIL`/`UNKNOWN` strictly, deriving a stable `judge_id`,
and reading log-probabilities. Every author shouldn't have to redo that.

## Decision

1. **The contract is a `typing.Protocol`** in `core/protocols.py`: `Judge`,
   `MultiCriterionJudge`, `Target`, `TraceSource`, `Store` and, later, `Embedder`.
   Any object with the right methods satisfies it (structural typing). No inheritance
   is required.
2. **Helper base classes are offered for convenience, never required.** For example,
   `judges/base.py` provides a `PromptJudge` base using the *template method* pattern: it
   renders, parses and hashes, and the subclass implements only the model call.
3. Helper base classes live in the **adapter** packages, never in `core/`. The core only
   defines shapes.
4. `@runtime_checkable` is used only where the code needs an `isinstance` check (for
   example, detecting a `MultiCriterionJudge`). Static checking by pyright is the main
   enforcement.

## Consequences

**Positive**

- A user's judge can be a plain class, or even a wrapper around their internal library,
  with no import from evalhawk required.
- Wrappers (decorator pattern: caching, recalibration, cascades) compose naturally,
  because anything shaped like a `Judge` can wrap anything else shaped like a `Judge`.
- Tests use simple fakes instead of mocks.

**Negative**

- Protocol mismatches are caught by the type checker, not at runtime, unless we check
  explicitly. The `wiring.py` layer validates plugins when it loads them and gives clear
  errors.
- We maintain two things per port (the Protocol, plus an optional helper), and they must
  stay consistent.

## Alternatives considered

| Option | Why not |
|---|---|
| Abstract base classes (`abc.ABC`) as the contract | Forces users to inherit from our classes; couples their code to our hierarchy |
| Duck typing without Protocols | No static checking; errors appear late and are hard to read |
| Plain callables everywhere | Too little structure for judges that need a stable `judge_id` and optional capabilities |

## References

- PEP 544, *Protocols: Structural subtyping*: <https://peps.python.org/pep-0544/>
- `docs/design/patterns.md`
