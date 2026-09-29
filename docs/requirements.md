# Requirements

This page lists **what** evalhawk must do (functional requirements) and **how well** it
must do it (non-functional requirements). Every requirement has an ID, so tests, pull
requests and ADRs can refer to it (for example, "implements FR-5").

- **Functional** is *what* the car does: drives, brakes, steers.
- **Non-functional** is *how well*: 0–100 in 8 s, a 5-star safety rating. Every NFR here is
  **measurable**, so a test or a benchmark can check it.

Stages refer to the build order in [ADR-0007](decisions/0007-build-order.md) and the
[roadmap](roadmap.md).

## Functional requirements

### Data in

| ID | Requirement | Stage |
|---|---|---|
| FR-1 | Import examples and traces from JSONL and CSV. Import streams through iterators and inserts in batches, so file size is limited by disk, not memory. | C |
| FR-2 | Re-importing the same data creates no duplicates (content-addressed IDs, [ADR-0006](decisions/0006-content-addressed-ids-and-splits.md)). | C |
| FR-3 | Validate data shape at load time for each evaluation kind (`single_turn`, `rag`; later `pairwise`, `agent`). Errors name the row and the missing field. | C |
| FR-4 | `--sample N` evaluates a reproducible random subset of a large dataset. | E |
| FR-5 | Import traces from Langfuse and OpenTelemetry (extras `[langfuse]`, `[otel]`). | I |

### Criteria, evaluations and splits

| ID | Requirement | Stage |
|---|---|---|
| FR-6 | Define binary criteria (id, question, version). Editing a criterion creates a new version; old labels stay attached to the old version ([ADR-0003](decisions/0003-binary-criteria-only.md)). | C |
| FR-7 | Define an **Evaluation**: dataset, kind, criterion→judge mapping, estimator (Rogan-Gladen or PPI). | C |
| FR-8 | Assign each example (or `group_id`) to train, dev or test deterministically. Splits can never change once assigned. | C |
| FR-9 | Log every read of the test split, with its purpose. | C |

### Running and judging

| ID | Requirement | Stage |
|---|---|---|
| FR-10 | Run the user's app through a Python callable, an HTTP endpoint (`HttpTarget`: url, headers with `${ENV}` expansion, `{{input}}` body template, `answer_path`, `contexts_path`, timeout), an OpenAI-compatible API, or pre-recorded outputs. | E |
| FR-11 | Grade each (trace, criterion) with any object satisfying the `Judge` protocol. Outcomes are PASS, FAIL or UNKNOWN, with an optional probability. | E |
| FR-12 | Built-in judges: `OpenAICompatibleJudge` (any `base_url`; options `headers`, `verify` CA bundle, `timeout`; probability from logprobs when available) and `FunctionJudge`. | E |
| FR-13 | Cache verdicts on `(trace_id, criterion_id, judge_id)`. A rerun makes zero repeated calls. | E |
| FR-14 | `repeats = k` runs each example k times; the statistics treat repeats as a cluster. | E |
| FR-15 | Stop scheduling calls when the projected spend would exceed `max_cost_usd`. | E |

### Human labels and calibration

| ID | Requirement | Stage |
|---|---|---|
| FR-16 | Blind labeling UI: the judge's verdict is never shown while a human labels. Keys `P`, `F`, `U`, `→`, plus a notes field. | F |
| FR-17 | Queue strategies (random, uncertain-first, disagreement-first) record each item's inclusion probability; estimators use inverse-probability weights. | F |
| FR-18 | Keep a **Calibration** record per (judge, criterion): sensitivity, specificity, n, date, status. | E |
| FR-19 | Mark a calibration **stale** when the `judge_id` changes, when there are too few labels, or when Rogan-Gladen and PPI disagree beyond their intervals. `evalhawk judges status` shows it. | E |
| FR-20 | `evalhawk judges compare` shows agreement and calibration side by side for several judges on the same criterion. | E |

### Results

| ID | Requirement | Stage |
|---|---|---|
| FR-21 | Report agreement (sensitivity, specificity, precision, Cohen's kappa), each with a Wilson CI. | B |
| FR-22 | Report a corrected pass rate (Rogan-Gladen or PPI) with CI, n and UNKNOWN rate. | B |
| FR-23 | **Refuse** to correct when sensitivity + specificity − 1 ≤ 0.1, and explain why. | B |
| FR-24 | Use cluster-robust intervals when examples share a `group_id` or are repeats. | B |
| FR-25 | Report calibration for probabilistic judges: reliability bins, ECE (with the bin count), Brier score. | B |
| FR-26 | `evalhawk eval` = run + judge + report in one command. `evalhawk report` reports on stored results. | D/E |
| FR-27 | `evalhawk export` writes verdicts, labels and results to CSV or JSONL. | E |
| FR-28 | `evalhawk compare` pairs traces by `example_id` and returns BETTER, WORSE or INCONCLUSIVE, plus "need about N more examples". Exit codes: 0 ok, 1 significant regression, 2 error. | H |

### Later features

| ID | Requirement | Stage |
|---|---|---|
| FR-29 | `CascadeJudge`: a cheap judge escalates to a strong one below a threshold chosen on dev. It is itself a `Judge`. | G |
| FR-30 | Cluster human notes and judge reasoning to propose new criteria; a human confirms each one. | I |
| FR-31 | RAG criteria (faithfulness, answer relevance, context relevance) and retrieval metrics (recall@k, MRR, nDCG). | I |
| FR-32 | Third-party adapters register through Python entry points and are usable from config by name. | E |

## Non-functional requirements

| ID | Quality | Requirement | How it's checked |
|---|---|---|---|
| NFR-1 | **Correctness** | 95% intervals contain the true value in 93.5–96.5% of 2,000 simulated runs, for every estimator | `tests/validation/` (marked `slow`), before each release |
| NFR-2 | **Correctness** | PPI results match `ppi-python` within 1e-6 | Oracle test (dev-only dependency) |
| NFR-3 | **Correctness** | Property tests hold: `low ≤ point ≤ high`; results don't depend on input order; intervals shrink as n grows | Hypothesis |
| NFR-4 | **Honesty** | No public function returns a point estimate without an interval; every estimate reports its UNKNOWN rate | Type signatures (`-> Estimate`), review |
| NFR-5 | **Reproducibility** | Same data, config and seed give an identical report on any OS. Every run stores a manifest (config, judge IDs, package version, git SHA, seed) | Integration test on Windows and Linux CI |
| NFR-6 | **Stability** | `content_id`, `judge_id` and split assignment never change within a major version | Golden tests ([ADR-0006](decisions/0006-content-addressed-ids-and-splits.md)) |
| NFR-7 | **Reliability** | A crashed run resumes with zero repeated paid calls. Retries use exponential backoff with jitter on 429/5xx. Failed jobs are recorded, never silently dropped | Integration test with a fake judge that fails |
| NFR-8 | **Cost** | Spend never exceeds `max_cost_usd` by more than the calls already in flight | Unit test on the budget |
| NFR-9 | **Performance**¹ | On a laptop: import 100k traces in under 60 s; report on 100k verdicts in under 5 s; 2,000 bootstrap resamples over 10k items in under 2 s | Benchmarks (from Stage C) |
| NFR-10 | **Concurrency** | The CLI and the UI use one database at the same time without "database is locked" errors | Integration test with two connections |
| NFR-11 | **Security** | API keys are read only from environment variables named in config; they never reach the database, logs or manifests. TLS verification is on by default | A test searches the DB and logs for a sentinel key |
| NFR-12 | **Privacy** | No telemetry. Data is sent only to endpoints the user configured. An optional `redact` hook runs before any external call | Review; unit test on the hook |
| NFR-13 | **Portability** | Windows, Linux and macOS; Python 3.11–3.13; no GPU, no torch, no compiler | CI matrix |
| NFR-14 | **Lean install** | The core install needs only pydantic, numpy, scipy and typer. Everything else is an optional extra, imported lazily; `import evalhawk` never fails because an extra is missing | Test in a core-only environment |
| NFR-15 | **Usability** | 100 labels take under 15 minutes. Every error message says what went wrong, where, and how to fix it | Timed session; review |
| NFR-16 | **Maintainability** | pyright strict on `core/` and `stats/`; test coverage ≥ 90% on `core/` and `stats/`, ≥ 80% overall; layer contracts pass | CI |
| NFR-17 | **Documentation** | Every public function and class has a docstring; every user-visible change has a CHANGELOG entry; the docs build has no warnings | CI (`zensical build --strict`), PR template |

¹ The performance targets are initial proposals. They will be benchmarked in Stage C and
adjusted here, with a note on the change.

## Out of scope

evalhawk will **not**: host or store the user's traces long-term, replace an observability
platform, offer Likert-scale grading, let users supply their own estimators
([ADR-0002](decisions/0002-thin-edges-thick-core.md)), or require any particular model
vendor or database.
