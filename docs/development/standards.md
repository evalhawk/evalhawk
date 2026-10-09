# Engineering standards

The rules every change to evalhawk follows. Most are enforced automatically by ruff,
pyright, import-linter, pytest and CI; the rest are checked in review.

**Why so strict?** evalhawk's product is *trustworthy numbers*. A tool that tells other
people their numbers are wrong has to be very sure about its own. These standards exist to
make mistakes hard to make and easy to catch.

For the reasoning behind the structure, see [Design patterns and intuitions](../design/patterns.md).

## 1. Architecture rules

1. **Imports point inward** ([ADR-0005](../decisions/0005-package-layout.md)). `core/` and
   `stats/` never import adapters, services, the CLI, I/O libraries or vendor SDKs.
   `import-linter` enforces this.
2. **Only `wiring.py` constructs concrete adapters.** Everything else receives them as
   parameters (dependency injection).
3. **Protocols are the contract** ([ADR-0004](../decisions/0004-protocols-and-helper-base-classes.md)).
   Depend on `Judge`, never on `OpenAICompatibleJudge`.
4. **No `utils.py` or `helpers.py`.** If a function has no obvious home, the design is
   missing a concept. Discuss it.
5. **Create a package only in the phase that needs it.**

## 2. Python style

- Formatting is automatic (`ruff format`, line length 100). Don't argue with the formatter.
- Lint rules: `E, W, F, I, B, UP, SIM, N, PT, RUF` (see `pyproject.toml`).
- Naming:

| Thing | Style | Example |
|---|---|---|
| Modules, functions, variables | `snake_case` | `corrected_pass_rate` |
| Classes, Protocols, type aliases | `PascalCase` | `CascadeJudge`, `Outcome` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_CONFIDENCE` |
| Internal (not public API) | leading underscore | `_two_sample_bootstrap` |

- Names say what a thing **is**, in domain words: `sensitivity`, not `tpr_val` or `x2`.
  Statistical symbols are fine inside a function when the docstring defines them
  (`s`, `c`, `theta`).
- Absolute imports only (`from evalhawk.core.models import Verdict`). No wildcard imports.
- Keyword-only arguments (`*`) for anything optional or easily confused:
  `wilson_interval(k, n, *, confidence=0.95)`.

## 3. Types

- Every function signature is fully annotated, including the return type.
- `core/` and `stats/` pass **pyright strict**. The rest passes pyright standard.
- No `Any` in `core/` or `stats/`. Use NumPy's typed arrays (`npt.NDArray[np.float64]`).
- A type-checker suppression needs the rule name **and** a reason:
  `x = f()  # pyright: ignore[reportUnknownMemberType]  # numpy stub gap, see #12`.

## 4. Data and value objects

- **Domain models** (`core/models.py`): Pydantic v2 with
  `model_config = ConfigDict(frozen=True, extra="forbid")`. Immutable, and unknown fields
  are rejected.
- **Statistics results** (`core/results.py`): frozen dataclasses with `slots=True`, validated
  in `__post_init__` (for example `low ≤ high`, finite values). `stats/` never imports Pydantic.
- Models hold data and validation only. No I/O methods (`.save()`, `.fetch()`) on models.

## 5. Statistics code (`stats/`)

- **Pure functions:** arrays in, frozen dataclass out. No I/O, no global state, no printing.
- **Randomness is injected:** every function that samples takes a keyword-only
  `rng: np.random.Generator`. Never call `np.random.default_rng()` or `np.random.*` inside
  `stats/`.
- **Never return a bare point estimate.** Estimates return `Estimate` (point, low, high,
  n, method, UNKNOWN rate).
- **Validate inputs at the top:** shapes match, values are 0/1 where binary, n > 0. Raise
  `ValueError` with the offending value.
- **Refuse rather than mislead:** for example, no Rogan-Gladen correction when
  `sensitivity + specificity − 1 ≤ 0.1`.
- **The docstring states** the formula, its assumptions, and a reference (paper or textbook).
- **Every estimator ships with** a unit test with known values, property tests, and a coverage
  simulation (see section 9).

## 6. Errors

- All our exceptions inherit from `EvalhawkError` (`core/errors.py`), with subclasses such as
  `ConfigError`, `DataError`, `JudgeError`, `StoreError`.
- Every message answers **what** went wrong, **where**, and **how to fix it**:
  > `DataError: evaluation 'support-rag' is kind=rag, but row 12 of data/eval.jsonl has no
  > 'contexts' field (37 rows affected). Add 'contexts' or set kind = "single_turn".`
- Never write `except:` or `except Exception: pass`. Catch the narrowest exception you can
  handle, and re-raise with context (`raise DataError(...) from exc`).
- Fail early: validate config and data shapes before making any paid call.

## 7. Async, I/O and logging

- `Judge.judge` and `Target.__call__` are `async`. A synchronous user function is wrapped
  with `asyncio.to_thread`. No blocking I/O inside `async def`.
- Concurrency limits, retries and timeouts live in `runner/`, not in each adapter.
- Use `logging.getLogger(__name__)`. No `print` outside `cli/`.
- **Never log secrets.** API keys come from environment variables named in config
  (`api_key_env`), and are never stored, logged or included in manifests.
- Optional dependencies are imported **lazily** inside the adapter, with a helpful error:
  > `ImportError: OpenAICompatibleJudge needs the 'llm' extra: pip install "evalhawk[llm]"`

## 8. Dependencies

- Core runtime dependencies are pydantic, numpy and typer. Adding one **requires an ADR**.
- Integrations go in optional extras (`[llm]`, `[jev]`, `[ui]`, `[cluster]`, `[langfuse]`,
  `[otel]`), added in the phase that first needs them.
- Dev tools go in dependency groups (`dev`, `docs`). Exact versions are pinned by `uv.lock`,
  which is always committed. Use `uv add`, never hand-edit the lockfile.
- Before adding or upgrading anything, check its current version and maintenance status.

## 9. Testing

| Folder | What | Rules |
|---|---|---|
| `tests/unit/` | One behaviour per test; mirrors `src/` | Fast, no network, no disk except `tmp_path` |
| `tests/property/` | Hypothesis invariants for `stats/` and `core/` | Fixed or recorded seeds |
| `tests/validation/` | Coverage simulations, `ppi-python` oracle | Marked `@pytest.mark.slow` |
| `tests/integration/` | Store + services + runner with fakes | Temporary SQLite |
| `tests/fixtures/` | Sample data, recorded HTTP responses | No real user data |

- Test names describe behaviour: `test_splits_cannot_be_updated_once_assigned`.
- **Fakes over mocks:** use `evalhawk.testing.FakeJudge` (known sensitivity and specificity)
  rather than patching internals.
- **Golden tests** freeze one-way doors (content IDs, judge IDs, split assignment).
- Markers: `slow` (validation suite: nightly and before release), `live` (real APIs: never
  in CI). CI runs `-m "not slow and not live"`.
- Coverage targets: ≥ 90% on `core/` and `stats/`, ≥ 80% overall.
- A bug fix starts with a failing test that reproduces the bug.

## 10. Docstrings and docs

- Google-style docstrings on every public module, class and function: a one-line summary,
  then `Args:`, `Returns:`, `Raises:`, and an `Example:` where it helps.
- Docs explain **simply first** (an analogy or a concrete example), then technically.
- A user-visible change updates the docs in the **same** pull request.

## 11. Git and collaboration

- `main` is protected: every change goes through a pull request, CI must be green, and the
  **other** maintainer approves.
- Branch names: `feat/…`, `fix/…`, `docs/…`, `refactor/…`, `test/…`, `chore/…`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat(stats): add Wilson interval`, `fix(storage): enable foreign keys per connection`.
- Pull requests are small and focused (ideally under about 400 changed lines, excluding
  tests and lockfile). Squash-merge.
- pre-commit runs locally before every commit. Install it once with
  `uv run pre-commit install`.
- A one-way-door decision needs an ADR ([how](../decisions/index.md)).

## 12. Versioning and releases

- [Semantic Versioning](https://semver.org/). Before 1.0, a breaking change bumps the minor
  version and is called out in the CHANGELOG.
- [Keep a Changelog](https://keepachangelog.com/): user-visible changes go under
  `## [Unreleased]` in the same PR.
- **Deprecate before removing:** emit a `DeprecationWarning` for at least one minor release.
- Changing a one-way door ([ADR-0006](../decisions/0006-content-addressed-ids-and-splits.md))
  is a breaking change and needs a migration.

## 13. Definition of done

A change is done when:

- [ ] It does what the linked requirement or issue asks ([requirements](../requirements.md))
- [ ] Tests cover it (including property or validation tests for `stats/`)
- [ ] ruff, pyright, import-linter and pytest pass locally and in CI
- [ ] Public API has docstrings, and the docs are updated
- [ ] The CHANGELOG is updated if users would notice
- [ ] Any one-way-door decision has an ADR
- [ ] The other maintainer approved it
