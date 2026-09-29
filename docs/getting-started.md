# Getting started

EvalHawk isn't released yet. This page covers the **development setup**; the user
quickstart arrives with the first usable version.

## Prerequisites

- [uv](https://docs.astral.sh/uv/): it installs the right Python (3.12 for development)
  automatically, so your system Python version doesn't matter.
- Git.

## Set up

```bash
git clone https://github.com/evalhawk/evalhawk.git
cd evalhawk
uv sync --all-groups          # creates .venv with the package and all dev tools
uv run pre-commit install     # run the checks automatically on every commit
```

## Everyday commands

| Command | What it does |
|---|---|
| `uv run pytest` | Run the tests (add `-m "not slow"` to skip the long simulations) |
| `uv run ruff check .` | Lint |
| `uv run ruff format .` | Format code, including Python blocks in Markdown |
| `uv run pyright` | Type-check (strict on `core/` and `stats/`) |
| `uv run lint-imports` | Check the architecture's layer rules |
| `uv run zensical serve` | Preview these docs at <http://localhost:8000> |
| `uv run evalhawk --version` | Run the CLI |

!!! tip "Windows"
    If `uv` isn't found in PowerShell, add it to the path for the session:
    `$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"`

## Next

Read the [engineering standards](development/standards.md) before your first pull request.
