# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Before 1.0, a breaking change bumps the minor version and is marked **Breaking**.

## [Unreleased]

### Added

- MT-Bench human-judgments converter (`experiments/datasets/mtbench_human.py`): run the
  offline report on real GPT-4 verdicts against human experts.
- Offline services and CLI: synthetic `demo init`, recorded JSONL/CSV `import`,
  representative-case `report`, paired judge-proxy `compare`, split/read `audit`,
  latest-label majority adjudication, run manifests and explicit run selection.
  Rich is a direct CLI dependency; ADRs 0011 and 0012 remain Proposed.
- Schema 2 scalar outcome reads and forward migration from populated schema 1.
- Adaptive bootstrap batches and singleton-cluster reduction, with million-item
  peak-allocation regression tests. Memory remains O(n), not constant or six MB total.
- Data backbone (D2-D7): validated models, normalized text identities, group-aware split
  sets, sync Store protocols, transactional SQLite, streaming JSONL/CSV sources, tags,
  split diagnostics and offline fakes. ADR-0010 is Proposed pending maintainer review.
- Coverage simulations (card S7): fixed-seed slow tests for naive, Rogan–Gladen, PPI,
  and clustered intervals, plus a standalone theta-grid coverage plotting script.
- Cluster-robust standard errors, clustered bootstrap options and `required_n_paired()` for sample-size planning (card S6).
- Prediction-powered inference for mean estimation (card S5): `ppi_mean()` with unbiased
  point estimate and confidence interval.
- Version comparison (card S4): `mcnemar_exact()`, `paired_bootstrap()`, `decide()` and the `Comparison` result object.
- Rogan-Gladen judge correction (card S3): `rogan_gladen()`, `corrected_pass_rate()` and `JudgeTooWeakError`.
- Judge agreement metrics (card S2): `Confusion` dataclass, `confusion()`, `sensitivity()`,
  `specificity()`, and `cohen_kappa()` with bootstrap confidence intervals.
- `wilson_interval()` confidence interval for binomial proportions (card S1).
- `Estimate` result value object and the `EvalhawkError` exception hierarchy (card J1).

- Project foundation: `src/` layout, `evalhawk --version` CLI, uv, ruff, pyright
  (strict on `core/` and `stats/`), pytest, Hypothesis, import-linter layer rules,
  pre-commit hooks.
- CI on Python 3.11, 3.12 and 3.13 on Linux and Windows; strict docs build; docs
  deployment to GitHub Pages.
- Documentation site (Zensical): requirements, roadmap, architecture, design patterns,
  engineering standards, limitations, and architecture decision records 0001–0009.
- "Evaluating AI systems" guide (planned evals per system type) and a features comparison.
- MIT license; maintainer agreement, work plan with task cards, and dev log for the two maintainers.

### Changed

- `normalize_text()` also applies Unicode NFC; `content_id()` itself is unchanged.
- SciPy is no longer a runtime dependency (ADR-0009).
