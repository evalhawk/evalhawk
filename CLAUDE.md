# CLAUDE.md: evalhawk

Context for Claude Code sessions in this repo. Read this first, then `docs/roadmap.md` and `docs/architecture.md`.

## What this is

**evalhawk** is an open-source Python tool (target: `pip install evalhawk`) for trustworthy LLM evaluation:
- calibrate LLM judges (including cheap ones like TypeSafe's JEV) against **blind human labels**
- report **bias-corrected** pass rates (Rogan-Gladen, PPI) **with confidence intervals**
- run **paired** v1-vs-v2 comparisons ("better / worse / inconclusive, need N more")
- works with any OpenAI-compatible model, the user's HTTP API, or pre-recorded outputs; RAG support later

Pitch: *"Bring your own model, judge and data. We make the eval numbers trustworthy."*
It's also both maintainers' flagship portfolio project for LLM/GenAI engineer roles, so code quality, tests and docs matter as much as features.

## Maintainers and how to help them

Two equal co-owners, both using Claude Code with this file:

| Maintainer | GitHub | Current track (see `docs/development/workplan.md`) |
|---|---|---|
| Venkata Sai Karthik | EVSGoud | Track 2: data backbone (`core/`, `storage/`, `sources/`, `testing/`, cards D1–D7; then X1) |
| Krishna Nandimandalam | kclectic0501 | Track 1: statistics engine (`stats/`, cards S1–S7; then X2) |

- **Follow the maintainer agreement** (`docs/development/collaboration.md`), especially §6 on AI use: the human must be able to explain every line; the human checks the tests; never push or merge without review; never put secrets or private data into prompts.
- **Work from a card.** When a maintainer starts a task, read its card in `docs/development/workplan.md`. Explain the concept simply first, then write tests, then code. Stay inside that card's files; if a change touches the other track, say so explicitly so the PR can tag the other maintainer.
- **Before executing a multi-step phase, present a to-do list and get confirmation.**
- Explain new concepts **simply first** (analogies, concrete examples), then technically.
- **Verify fast-moving facts** (libraries, versions, papers) with web search and cite sources. Don't rely on memory.
- **Lean dependencies**: optional extras, no torch, no heavy frameworks without a reason. New runtime dependencies need an ADR approved by both.
- Say plainly when earlier advice was wrong.
- At the end of a card, help write the PR description (including "What I learned" and "How AI was used") and the dev-log entry (`docs/devlog/template.md`).
- **Naming:** `evalhawk` (lowercase, no hyphen) for package, import, GitHub org `evalhawk` and repo `evalhawk/evalhawk`; **EvalHawk** as the display brand.
- Both develop on laptops (no GPU; use Ollama or free API tiers for LLM calls).

## Architecture rules (see docs/architecture.md)

- **Ports and adapters.** `core/` and `stats/` import nothing from vendors or I/O. Adapters implement `typing.Protocol`s: `Judge`, `Target`, `TraceSource`, `Store`.
- **Protocols are the contract**; optional helper base classes are offered for convenience, never required.
- **Thin edges, thick core.** Users can swap models/judges/data sources/stores, but never the statistics, blind labeling, or split locking.
- `stats/` = pure functions, arrays in and frozen dataclasses out, with an explicit `np.random.Generator`. Never report a point estimate without an interval.
- Splits are per *example* (or `group_id`), hash-based, and **immutable** (enforced by DB triggers). Reads of the test split are logged.
- Binary criteria only (PASS/FAIL/UNKNOWN). One criterion = one failure mode. Calibration belongs to a **(judge, criterion)** pair.
- Default store: SQLite (WAL, `busy_timeout`, `PRAGMA user_version` migrations). The user's own data stays where it is; we store only evaluation state.

## Stack

Python ≥3.11 (dev 3.12) · uv · hatchling · Pydantic v2 · NumPy · SciPy (test only, ADR-0009) · Typer · stdlib sqlite3 · TOML config.
Dev: pytest, pytest-cov, hypothesis, ruff, pyright (strict on core/ and stats/), pre-commit.
Docs: **Zensical** (`zensical.toml`). Material for MkDocs reaches end-of-life in Nov 2026, so don't use it.
Planned extras: `[llm]` openai · `[jev]` typesafe-sdk · `[ui]` fastapi+uvicorn+jinja2+vendored htmx 2 · `[cluster]` fastembed+scikit-learn · `[langfuse]` · `[otel]`. Dev-only oracle: `ppi-python`.

## Commands

```bash
uv sync --all-groups
uv run pytest                       # add -m "not slow" for fast runs
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run lint-imports                 # layer rules
uv run zensical serve               # docs preview; `zensical build --strict` in CI
uv run evalhawk --version
```

Always use `uv run` (never the system `python`). On Windows, if `uv` isn't found, add `%USERPROFILE%\.local\bin` to PATH, e.g. in PowerShell: `$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"`.

## Current status (2026-10-17): Stages A–D done (offline demo on synthetic data)

**On `main`:** foundation + CI (PRs #22–#25). D1 content IDs; J1 `Estimate`/errors; S1–S7 statistics
engine incl. the coverage simulation; D2–D7 data backbone (models, splits, protocols, SQLite store,
JSONL/CSV import, fakes); X1 services and an offline CLI: `evalhawk demo init`, `import`, `report`,
`compare`, `audit` (see `docs/getting-started.md`). 335 tests (23 marked `slow`), ~92% coverage,
4 import-linter contracts. ADRs 0001–0009 Accepted; **0010–0012 Proposed** (data-backbone contracts
incl. NFC + LF normalization of user text before hashing; offline report contract; `rich` as a
runtime dependency): both maintainers must accept or revise them.

**Pair work:** the maintainers sometimes pair on one laptop, so git may show only one author. For pair
commits add `Co-authored-by: Venkata Sai Karthik <venkatsai.karthik.goud@gmail.com>` (or Krishna's
equivalent) so both get credit.

**Open:** #17 X2 (DeepEval mapping + MT-Bench converter remain), #18 X3 (demo runs on synthetic data;
public human-labelled dataset + README GIF remain), #2 PyPI name (deferred by Karthik), #3 branch
protection. Maintainer agreement: Krishna signed (10 h/week); Karthik's sign-off and hours pending.

**Next:** finish X2/X3 on MT-Bench human judgments, then Phase 4 (live judges via Ollama, runner with
the judgment-key cache, targets). Present a to-do list and a fair split between both maintainers first.

**Design note for the Phase 4 runner (agreed 2026-10-01):** keep verdicts keyed by
`(trace_id, criterion_id, judge_id)`, but look up reuse by a *judgment key* = content_id of everything
the judge sees (input, reference, output, contexts, criterion, judge), excluding run/version and repeat,
so identical answers across versions and repeats are never paid for twice.
