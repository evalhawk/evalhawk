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

## Current status (2026-09-29): Phase 0 nearly done

**Done (verified locally, not yet committed):**
- `uv sync --all-groups`; ruff, ruff format, pyright, import-linter, pytest all pass; `zensical build --strict` clean.
- `git init -b main` (no commits yet).
- `.pre-commit-config.yaml` (pre-commit-hooks v6.0.0 + local `uv run` hooks for ruff, pyright, lint-imports), installed.
- `.github/workflows/ci.yml` and `docs.yml`, `.github/pull_request_template.md`. Action versions checked 2026-09-27: `actions/checkout@v7`, `astral-sh/setup-uv@v10.2.0` (**setup-uv no longer publishes floating major tags: pin the full version**), `configure-pages@v6`, `upload-pages-artifact@v5`, `deploy-pages@v5`.
- `import-linter` (dev) with contract 1 active (core/stats purity). Contracts 2 and 3 are commented out in `pyproject.toml` until `services/`, `runner/` and adapters exist (import-linter requires source packages to exist).
- ruff 0.16 formats Python code blocks inside Markdown too; docs examples follow code style.
- Docs: `zensical.toml`, `docs/index.md`, `getting-started.md`, `requirements.md` (FR/NFR with IDs), `limitations.md`, `design/patterns.md` (LLD + 10 intuitions), `development/standards.md`, `decisions/` (template + index + ADR 0001–0008; **0007 build order is Proposed**, awaiting owner confirmation). `roadmap.md` and `architecture.md` renamed to evalhawk and updated with the agreed design additions and the new package tree.
- Root: `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`; README updated (brand EvalHawk).
- GitHub org `evalhawk` created; `pyproject.toml` URLs point to `evalhawk/evalhawk` and `evalhawk.github.io/evalhawk`.

**Remaining Phase 0 steps:**
1. ✅ `LICENSE` (MIT, "Venkata Sai Karthik and Krishna Nandimandalam"), `authors`, Zensical copyright.
2. ✅ Maintainer agreement, work plan (cards J1, S1–S7, D1–D7, X1–X3), dev log, PR template. Both must approve the agreement, ADR-0007 (parallel tracks) and ADR-0009 (no SciPy at runtime) in the first PR review.
3. ✅ Krishna's handle `kclectic0501` added; `.github/CODEOWNERS` requests both maintainers on every PR. Krishna must accept the org invite as **Owner**.
4. First commit (end the message with the Co-Authored-By line from the session), create the **public** repo `evalhawk/evalhawk`, push, confirm CI green. **Ask Karthik how:** install `gh` via winget + `gh auth login`, or create it on github.com. Then: Settings → Pages → Source "GitHub Actions"; enable private vulnerability reporting; branch protection on `main` (PR, green CI, 1 approval); create GitHub issues from the work-plan cards.
5. Publish `0.0.1` to PyPI to secure the name (a PyPI account with 2FA; both maintainers become Owners).
6. If ADR-0009 is accepted: move `scipy` from `dependencies` to the `dev` group.

**Then J1 (pair), followed by the parallel tracks in `docs/development/workplan.md`.** Present a to-do list first.
