## What and why

<!-- One or two sentences. Link the card: "Closes #<issue>" (card S1 in docs/development/workplan.md). -->

## How it was tested

<!-- Commands run, new tests, reference values checked. -->

## What I learned

<!-- The concept in two or three plain sentences. The reviewer uses this to check understanding. -->

## How AI was used

<!-- What you asked Claude Code for, what you changed or rejected. "Not used" is fine. -->

## Checklist

- [ ] Tests added or updated (property / validation tests for anything in `stats/`)
- [ ] `uv run pytest`, `ruff`, `pyright` and `lint-imports` pass locally
- [ ] I can explain every line in this PR
- [ ] Docstrings written; docs updated if behaviour or public API changed
- [ ] Dev-log entry added (`docs/devlog/`) if this finishes a card
- [ ] `CHANGELOG.md` entry under **Unreleased** (if users would notice)
- [ ] New one-way-door decision? Then an ADR in `docs/decisions/`
