# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Before 1.0, a breaking change bumps the minor version and is marked **Breaking**.

## [Unreleased]

### Added

- Project foundation: `src/` layout, `evalhawk --version` CLI, uv, ruff, pyright
  (strict on `core/` and `stats/`), pytest, Hypothesis, import-linter layer rules,
  pre-commit hooks.
- CI on Python 3.11, 3.12 and 3.13 on Linux and Windows; strict docs build; docs
  deployment to GitHub Pages.
- Documentation site (Zensical): requirements, roadmap, architecture, design patterns,
  engineering standards, limitations, and architecture decision records 0001–0009.
- "Evaluating AI systems" guide (planned evals per system type) and a features comparison.
- MIT license; maintainer agreement, work plan with task cards, and dev log for the two maintainers.
