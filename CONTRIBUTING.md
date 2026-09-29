# Contributing to evalhawk

Thanks for helping. evalhawk's product is *trustworthy numbers*, so we hold the code to a
high bar. This page gets you from zero to a merged pull request.

## Set up (once)

You need [uv](https://docs.astral.sh/uv/) and Git. uv installs the right Python for you.

```bash
git clone https://github.com/evalhawk/evalhawk.git
cd evalhawk
uv sync --all-groups          # .venv with the package and all dev tools
uv run pre-commit install     # checks run automatically on every commit
```

## Everyday commands

```bash
uv run pytest                 # tests (add -m "not slow" to skip long simulations)
uv run ruff check .           # lint
uv run ruff format .          # format (also Python blocks in Markdown)
uv run pyright                # type-check (strict on core/ and stats/)
uv run lint-imports           # architecture layer rules
uv run zensical serve         # docs preview at http://localhost:8000
```

## Workflow

1. **Start from an issue** or a roadmap item, so the work is agreed before it's written.
2. **Branch** from `main`: `feat/…`, `fix/…`, `docs/…`, `refactor/…`, `test/…`, `chore/…`.
3. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/):
   `feat(stats): add Wilson interval`.
4. **Open a pull request.** Keep it small and focused, and fill in the template.
5. **CI must be green**, and the **other maintainer approves** before merging.
   `main` is protected; nobody pushes to it directly.
6. **Squash-merge.**

## Before you open a pull request

- Read the [engineering standards](docs/development/standards.md). The short version:
  - Imports point inward: `core/` and `stats/` never import adapters, I/O or vendor SDKs.
  - Statistics return an `Estimate` (with an interval), never a bare number.
  - Randomness is passed in as `rng: np.random.Generator`.
  - Errors say what went wrong, where, and how to fix it.
- Add tests. A bug fix starts with a test that reproduces the bug.
- Update the docs and `CHANGELOG.md` (under **Unreleased**) if users would notice.
- A decision that's hard to undo needs an [ADR](docs/decisions/index.md).

## Where things are

| You want to... | Look in |
|---|---|
| Understand what we're building and why | [Requirements](docs/requirements.md), [Roadmap](docs/roadmap.md) |
| Understand how it fits together | [Architecture](docs/architecture.md), [Design patterns](docs/design/patterns.md) |
| Know why a decision was made | [Decision records](docs/decisions/index.md) |

## Reporting bugs and security issues

- Bugs and feature ideas: [GitHub issues](https://github.com/evalhawk/evalhawk/issues).
- Security issues: **don't open a public issue.** See [SECURITY.md](SECURITY.md).

By contributing, you agree that your contributions are licensed under the project's
[MIT License](LICENSE).
