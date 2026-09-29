# Architecture

> Companion to the [roadmap](roadmap.md), which covers **when** (phases and timeline). This document covers **how**: repository layout, architecture, data model, interfaces, the order of implementation, and the concepts you need to know. [Requirements](requirements.md) covers **what**, [Design patterns](design/patterns.md) is the low-level design, and the [decision records](decisions/index.md) explain **why**. Known limits are in [Limitations](limitations.md).

---

## Contents

1. [System overview](#1-system-overview)
2. [Repository structure](#2-repository-structure)
3. [Architecture](#3-architecture)
4. [Data model and storage schema](#4-data-model-and-storage-schema)
5. [Interfaces (the plug-in points)](#5-interfaces-the-plug-in-points)
6. [Key runtime flows](#6-key-runtime-flows)
7. [Statistics core: specification](#7-statistics-core-specification)
8. [Judges: specification](#8-judges-specification)
9. [Runner, caching and reliability](#9-runner-caching-and-reliability)
10. [Configuration and public API](#10-configuration-and-public-api)
11. [Testing strategy](#11-testing-strategy)
12. [Plan of action (technical, per phase)](#12-plan-of-action-technical-per-phase)
13. [Concepts you must know](#13-concepts-you-must-know)
14. [Reading list](#14-reading-list)

---

## 1. System overview

**Problem.** Teams grade LLM outputs with LLM judges and then trust the resulting numbers blindly. The judge's errors, sampling noise and correlated test questions all go unaccounted for, so "v2 is better than v1" is often just noise.

**What the system does.**

1. Runs the user's LLM app (the *target*) over a dataset, or imports outputs that already exist.
2. Grades each output against **binary criteria** using one or more **judges**.
3. Collects a small set of **blind human labels** through a fast labeling UI.
4. Measures how well each judge agrees with humans (TPR/TNR, calibration).
5. Reports **bias-corrected** pass rates and **paired comparisons** between versions, each with confidence intervals and a sample-size estimate.
6. Groups failures into clusters to suggest new criteria.

**What it deliberately does not do.** Host traces, replace an observability platform, or require a particular model, database or vendor.

---

## 2. Repository structure

The agreed layout ([ADR-0005](decisions/0005-package-layout.md)). Packages are created **in the phase that first needs them**; this is the map, not a to-do list.

```
evalhawk/
├── pyproject.toml  uv.lock  .python-version
├── README.md  LICENSE  CHANGELOG.md  CONTRIBUTING.md  SECURITY.md
├── zensical.toml  .pre-commit-config.yaml  .gitignore  .gitattributes
├── .github/
│   ├── workflows/            ci.yml · docs.yml · release.yml (Phase 9)
│   └── pull_request_template.md
│
├── docs/                     Zensical site source
│   ├── index.md  getting-started.md  requirements.md  limitations.md
│   ├── roadmap.md  architecture.md
│   ├── design/patterns.md    low-level design and intuitions
│   ├── development/standards.md
│   └── decisions/            ADRs: 0000-template.md, 0001–0008
│
├── src/evalhawk/
│   ├── __init__.py           public API re-exports ONLY
│   ├── __main__.py  py.typed
│   │
│   ├── core/                 DOMAIN: what things are (no I/O, no vendor SDKs)
│   │   ├── models.py         Example, Trace, Run, Criterion, Label, Verdict, Evaluation, Calibration
│   │   ├── protocols.py      Judge, MultiCriterionJudge, Target, TraceSource, Store, Embedder
│   │   ├── results.py        Estimate, Comparison (numbers + their intervals)
│   │   ├── ids.py            content-addressed IDs (sha256 of canonical JSON)
│   │   ├── splits.py         deterministic, group-aware split assignment
│   │   └── errors.py         EvalhawkError hierarchy
│   ├── stats/                MATH: pure functions, arrays in, frozen dataclasses out
│   │   ├── intervals.py      wilson, bootstrap (cluster-aware)
│   │   ├── agreement.py      confusion matrix, sensitivity/specificity, kappa
│   │   ├── correction.py     rogan_gladen, corrected_pass_rate, ppi_mean
│   │   ├── compare.py        mcnemar_exact, paired_bootstrap
│   │   ├── clustered.py      cluster-robust SE
│   │   ├── power.py          required sample sizes
│   │   ├── calibration.py    ECE, Brier, reliability bins, Platt, isotonic
│   │   ├── weighting.py      inverse-probability weights for active sampling
│   │   └── retrieval.py      recall@k, MRR, nDCG
│   │
│   ├── services/             USE CASES: one module per user action
│   │   └── evaluate · calibrate · estimate · compare · label_queue · export
│   │       cascade_eval · error_correlation
│   ├── runner/               ENGINE: async fan-out, retries, timeouts, budget, cache lookups
│   │
│   ├── judges/               ADAPTERS ─┐
│   │   ├── base.py           optional PromptJudge helper (template method, ADR-0004)
│   │   ├── templates/        versioned prompts (.md), incl. rag/
│   │   └── openai_compat · function · jev · cascade · recalibrated · cached
│   ├── targets/              callable · recorded · http · openai_compat
│   ├── sources/              jsonl · csv · langfuse · otel
│   ├── storage/              sqlite.py + migrations/0001_init.sql
│   │
│   ├── config.py             evalhawk.toml → typed config (Pydantic), ${ENV} expansion
│   ├── plugins.py            entry-point registry ("type = 'jev'" → class)
│   ├── wiring.py             COMPOSITION ROOT: config → live objects (the only place adapters are built)
│   ├── testing/              FakeJudge, FakeTarget, InMemoryStore (public, for users too)
│   │
│   ├── cli/                  main.py · commands/ · render.py (Rich output)
│   ├── ui/                   extra [ui]: FastAPI + Jinja2 + vendored htmx 2 (Phase 4)
│   └── clustering/           extra [cluster]: fastembed + HDBSCAN (Phase 7)
│
├── tests/
│   ├── unit/                 mirrors src/: unit/core/, unit/stats/, ...
│   ├── property/             Hypothesis
│   ├── validation/           coverage simulations, ppi-python oracle (@slow)
│   ├── integration/          full flow with fakes + temporary SQLite
│   └── fixtures/             sample data, recorded HTTP responses
│
├── experiments/              NOT shipped: dataset converters, study scripts, figures, Makefile
└── examples/                 01_quickstart · 02_custom_judge · 03_rag
```

### Why it's laid out this way

- **`src/` layout.** Tests run against the *installed* package, which catches packaging mistakes early.
- **`core/` and `stats/` import no I/O or vendor SDKs.** They are the most important code and the easiest to test, and they can never break because a vendor changed its API. `import-linter` enforces this in CI.
- **`services/` is the only place that joins storage to statistics.** Statistics functions take arrays, not database rows.
- **`wiring.py` is the only place that builds concrete adapters.** Everything else receives them (dependency injection), so tests swap in fakes trivially.
- **Every vendor integration sits behind an optional extra** and is imported lazily, so `import evalhawk` never fails because `openai` isn't installed.
- **No `utils.py`.** Every function belongs to a layer.

---

## 3. Architecture

### 3.1 Layers and the dependency rule

```
┌──────────────────────────────────────────────────────────────┐
│  Interfaces:     cli/          ui/          (GitHub Action)  │
├──────────────────────────────────────────────────────────────┤
│  Application:    services/     runner/      clustering/      │
├──────────────────────────────────────────────────────────────┤
│  Domain (core):  core/         stats/                        │
├──────────────────────────────────────────────────────────────┤
│  Adapters:       judges/ targets/ sources/ storage/ (plugins)│
└──────────────────────────────────────────────────────────────┘
```

**Dependency rule:** arrows point *inward*. `core/` and `stats/` depend on nothing inside the project except each other. Adapters implement protocols defined in `core/protocols.py`. The application layer receives adapters through **dependency injection**; it never imports a concrete adapter by name.

This is the **ports and adapters** (hexagonal) architecture:

- **Ports** are the `Protocol`s: `Judge`, `Target`, `TraceSource`, `Store`, `Embedder`.
- **Adapters** are the implementations: `OpenAICompatibleJudge`, `SQLiteStore`, `JSONLSource`, and so on.

### 3.2 Thin edges, thick core

| Pluggable (edges) | Fixed (core) |
|---|---|
| Target app, judge model, trace source, embedder, store backend | Statistical estimators, split locking, blind labeling, reporting rules |

Users can swap *where numbers come from*. They cannot swap *how the numbers are computed*. That guarantee is the product.

### 3.3 Plugin discovery

Third-party packages can register adapters without changing this codebase, using entry points in *their* `pyproject.toml`:

```toml
[project.entry-points."evalhawk.judges"]
acme = "acme_evalhawk:AcmeJudge"
```

`plugins.py` loads them with `importlib.metadata.entry_points(group="evalhawk.judges")`, and config can then refer to them with `type = "acme"`.

---

## 4. Data model and storage schema

### 4.1 Entities

```
Evaluation *──1 Dataset 1──* Example 1──* Trace *──1 Run
    │                            │           │
    │ criterion → judge          │           ├──* Verdict *──1 Criterion
    │                            │           └──* Label   *──1 Criterion
    │                            └──1 Split
    └── uses Calibration (one per judge × criterion)
```

| Entity | Meaning | Key fields |
|---|---|---|
| **Dataset** | A named collection of inputs | `id`, `name` |
| **Example** | One input, optionally with a reference answer | `id` (content hash), `input`, `reference?`, `group_id?`, `metadata` |
| **Run** | One execution of one target version | `id`, `target_version`, `config_snapshot`, `created_at` |
| **Trace** | The target's output for one example in one run | `id`, `example_id`, `run_id`, `output`, `contexts?`, `usage`, `latency_ms` |
| **Criterion** | One binary question = one failure mode | `id`, `name`, `question`, `version` |
| **Verdict** | A judge's decision on (trace, criterion) | `outcome`, `probability?`, `reasoning?`, `judge_id`, `cost_usd`, `latency_ms` |
| **Label** | A human's decision on (trace, criterion) | `outcome`, `annotator`, `note?`, `inclusion_prob` |
| **Split** | Which pile an example belongs to | `train` / `dev` / `test`, immutable |
| **Evaluation** | What to measure on a dataset, and how | `id`, `dataset_id`, `kind`, `criteria: {criterion_id: judge_name}`, `estimator` (`rogan_gladen` \| `ppi`), `repeats` |
| **Calibration** | How far one judge can be trusted on one criterion | `judge_id`, `criterion_id`, `sensitivity`, `specificity` (each with CI), `n`, `computed_at`, `status` |

**Evaluation kinds** define the data shape that is checked **at load time**, before any paid call. A failure names the row and the missing field:

| Kind | Required per example / trace | Phase |
|---|---|---|
| `single_turn` | `input`, `output` | 1 |
| `rag` | `input`, `output`, `contexts` (list of strings); optional `relevant_doc_ids` for retrieval metrics | 1 (checks), 8 (criteria) |
| `pairwise` | `input`, `output_a`, `output_b` | Later |
| `agent` | `input`, a list of trajectory steps | Later |

**Calibration status** is one of `ok`, `stale` or `insufficient`:

- **stale** when the judge's `judge_id` has changed since the calibration (new model, prompt or parameters), or when Rogan-Gladen and PPI disagree by more than their intervals allow (a sign that an assumption is broken, see [Limitations](limitations.md));
- **insufficient** when there are too few human labels in either class (the minimum count is a config option, with a conservative default);
- **ok** otherwise.

Reports show the status next to every corrected estimate, and `evalhawk judges status` lists all of them.

**Why `Example` and `Trace` are separate:** comparing v1 and v2 requires *pairing* outputs for the same input. Pairing happens on `example_id`. Paired tests are much more powerful than unpaired ones (see §13.4).

**Why splits attach to `Example`, not `Trace`:** an input must stay in the same pile across every run. Otherwise test-set information leaks into the judge prompt through another run's trace.

**`Outcome`** is an enum: `PASS`, `FAIL`, `UNKNOWN`. `UNKNOWN` is kept in storage but excluded from the estimators, and its rate is always reported.

### 4.2 SQLite schema (`migrations/0001_init.sql`, abridged)

```sql
PRAGMA journal_mode = WAL;          -- concurrent readers + one writer (CLI and UI together)
PRAGMA foreign_keys = ON;

CREATE TABLE examples (
  id          TEXT PRIMARY KEY,               -- sha256 of canonical input
  dataset_id  TEXT NOT NULL,
  input       TEXT NOT NULL,                  -- JSON
  reference   TEXT,
  group_id    TEXT,                           -- for clustered errors and group-aware splits
  metadata    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE splits (
  example_id  TEXT PRIMARY KEY REFERENCES examples(id),
  split       TEXT NOT NULL CHECK (split IN ('train','dev','test')),
  assigned_at TEXT NOT NULL
);
-- Splits can never be changed or deleted:
CREATE TRIGGER splits_no_update BEFORE UPDATE ON splits
  BEGIN SELECT RAISE(ABORT, 'splits are immutable'); END;
CREATE TRIGGER splits_no_delete BEFORE DELETE ON splits
  BEGIN SELECT RAISE(ABORT, 'splits are immutable'); END;

CREATE TABLE runs (
  id              TEXT PRIMARY KEY,
  target_version  TEXT NOT NULL,
  config_snapshot TEXT NOT NULL,              -- JSON, for reproducibility
  created_at      TEXT NOT NULL
);

CREATE TABLE traces (
  id          TEXT PRIMARY KEY,
  example_id  TEXT NOT NULL REFERENCES examples(id),
  run_id      TEXT NOT NULL REFERENCES runs(id),
  output      TEXT NOT NULL,
  contexts    TEXT,                           -- JSON list, used by RAG
  usage       TEXT,                           -- JSON: tokens, cost
  latency_ms  INTEGER,
  UNIQUE (example_id, run_id)
);

CREATE TABLE criteria (
  id        TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  question  TEXT NOT NULL,
  version   INTEGER NOT NULL
);

CREATE TABLE verdicts (                       -- doubles as the judge cache
  trace_id     TEXT NOT NULL REFERENCES traces(id),
  criterion_id TEXT NOT NULL REFERENCES criteria(id),
  judge_id     TEXT NOT NULL,                 -- hash of judge type + model + template + params
  outcome      TEXT NOT NULL CHECK (outcome IN ('PASS','FAIL','UNKNOWN')),
  probability  REAL,                          -- P(PASS), when available
  reasoning    TEXT,
  cost_usd     REAL,
  latency_ms   INTEGER,
  created_at   TEXT NOT NULL,
  PRIMARY KEY (trace_id, criterion_id, judge_id)
);

CREATE TABLE labels (
  id             TEXT PRIMARY KEY,
  trace_id       TEXT NOT NULL REFERENCES traces(id),
  criterion_id   TEXT NOT NULL REFERENCES criteria(id),
  outcome        TEXT NOT NULL CHECK (outcome IN ('PASS','FAIL','UNKNOWN')),
  annotator      TEXT NOT NULL,
  note           TEXT,
  inclusion_prob REAL NOT NULL DEFAULT 1.0,    -- probability the queue selected this item
  created_at     TEXT NOT NULL
);

CREATE TABLE test_access_log (                -- every read of the test split is recorded
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purpose TEXT NOT NULL,
  at TEXT NOT NULL
);
```

Migrations are tracked with `PRAGMA user_version`. Each connection sets `busy_timeout` (for example 5000 ms), so a writer waits instead of failing when another writer holds the lock.

---

## 5. Interfaces (the plug-in points)

`core/protocols.py`:

```python
from collections.abc import AsyncIterator, Iterable
from typing import Protocol, runtime_checkable

from evalhawk.core.models import (
    Criterion,
    Example,
    Label,
    Run,
    Trace,
    TargetOutput,
    Verdict,
)


@runtime_checkable
class Target(Protocol):
    """The user's LLM app. Called once per example."""

    async def __call__(self, example: Example) -> TargetOutput: ...


@runtime_checkable
class Judge(Protocol):
    """Grades one trace against one criterion."""

    @property
    def judge_id(self) -> str: ...  # stable; changes when the prompt/model/params change
    async def judge(self, trace: Trace, criterion: Criterion) -> Verdict: ...


@runtime_checkable
class MultiCriterionJudge(Judge, Protocol):
    """Optional capability: several criteria in one call (JEV prices this like one call)."""

    async def judge_many(self, trace: Trace, criteria: list[Criterion]) -> list[Verdict]: ...


class TraceSource(Protocol):
    """Imports existing outputs from wherever the user keeps them."""

    def load(self) -> Iterable[tuple[Example, Trace]]: ...


class Store(Protocol):
    def add_examples(self, examples: Iterable[Example]) -> None: ...
    def add_traces(self, run: Run, traces: Iterable[Trace]) -> None: ...
    def get_verdict(self, trace_id: str, criterion_id: str, judge_id: str) -> Verdict | None: ...
    def put_verdict(self, verdict: Verdict) -> None: ...
    def add_label(self, label: Label) -> None: ...
    def iter_paired(self, criterion_id: str, judge_id: str, split: str) -> AsyncIterator[...]: ...

    # ...reads return plain records; services/ turns them into NumPy arrays
```

A user's custom judge is about 10 lines:

```python
class MyCompanyJudge:
    judge_id = "mycompany-v3"

    async def judge(self, trace, criterion):
        ok, score = await our_internal_model(trace.output, criterion.question)
        return Verdict.from_judge(
            self, trace, criterion, outcome="PASS" if ok else "FAIL", probability=score
        )
```

### 5.1 Built-in targets (Phase 3)

Most users shouldn't have to write Python to connect their app. Four built-in `Target`s cover the common cases:

| Target | Use when | Key options |
|---|---|---|
| `CallableTarget` | The app is a Python function (sync or async) | `callable = "my_app.bot:answer"` |
| `RecordedTarget` | Outputs already exist (imported traces) | none: it replays stored outputs |
| `HttpTarget` | The app is behind an HTTP API | `url`, `method`, `headers` (values may use `${ENV_VAR}`), `body` template with `{{input}}` (and other example fields), `answer_path` and `contexts_path` (JSONPath-style selectors into the response), `timeout` |
| `OpenAICompatibleTarget` | The app *is* a model behind an OpenAI-compatible endpoint | `base_url`, `model`, `api_key_env`, `system_prompt`, sampling params |

`${ENV_VAR}` values are expanded when the config is loaded and are never written to the store, logs or run manifests (see §9).

---

## 6. Key runtime flows

### 6.1 Evaluate a version

```
evalhawk eval --version v2 [--sample N]
  1. Load config → wiring.py builds Target, Judges, Store (dependency injection)
  2. Check the data shape for the evaluation kind; fail before any paid call
  3. For each Example (splits assigned on first sight, then locked), `repeats` times:
        Target(example) → Trace                     [async, rate-limited]
  4. For each (Trace, Criterion, Judge):
        cache hit?  → reuse the stored Verdict
        cache miss? → Judge.judge() → store the Verdict
  5. Write a run manifest (config snapshot, judge_ids, package version, git SHA, seed)
  6. Report: corrected pass rate per criterion, with CI, n, UNKNOWN rate and calibration status
```

`evalhawk import` followed by `evalhawk report` does steps 2–6 for outputs (and optionally verdicts) that already exist, with no Target call.

### 6.2 Calibrate a judge

```
evalhawk label          (UI, blind)
  1. The queue picks traces from train/dev (strategy: random | uncertain | disagreement)
     and records inclusion_prob for each pick
  2. The human labels PASS/FAIL/UNKNOWN; the judge's verdict is never shown
evalhawk report judge --split dev    (while iterating on the judge prompt)
evalhawk report judge --split test   (once, at the end; the access is logged)
  → TPR, TNR, kappa, ECE, Brier, each with a CI
```

### 6.3 Estimate and compare

```
evalhawk report estimate --run v2 --criterion no_fabrication
  → corrected pass rate θ̂ with 95% CI (Rogan-Gladen or PPI), n, UNKNOWN rate

evalhawk compare --base v1 --candidate v2
  → pairs traces by example_id
  → paired difference with CI, McNemar p-value, cluster-robust if group_id is set
  → verdict: BETTER | WORSE | INCONCLUSIVE (+ "need ~N more examples")
  → exit code for CI: 0 = ok, 1 = significant regression, 2 = error
```

### 6.4 Inspect judges and export

```
evalhawk judges status                 → every (judge, criterion) Calibration: sens, spec, n, date, status
evalhawk judges compare --criterion X  → several judges side by side on the same labels
evalhawk export --format csv|jsonl     → verdicts, labels and results, for use in other tools
```

---

## 7. Statistics core: specification

All functions are **pure**: NumPy arrays in, a frozen dataclass out. Every function takes an explicit `rng: np.random.Generator` when randomness is involved, so results are reproducible.

```python
@dataclass(frozen=True)
class Estimate:
    point: float
    low: float
    high: float
    confidence: float
    n: int
    method: str  # e.g. "wilson", "rogan_gladen+bootstrap", "ppi"
```

| Function | Module | Purpose |
|---|---|---|
| `wilson_interval(k, n, confidence=0.95)` | `intervals` | CI for a proportion (§13.2) |
| `bootstrap_ci(stat_fn, *arrays, n_boot, rng, clusters=None)` | `intervals` | Generic percentile bootstrap, cluster-aware |
| `confusion(human, judge)` / `tpr_tnr(...)` / `cohen_kappa(...)` | `agreement` | Judge vs human agreement (§13.1) |
| `rogan_gladen(q, sens, spec)` | `correction` | Point correction (§13.3) |
| `corrected_pass_rate(judge_test, judge_cal, human_cal, *, weights, rng)` | `correction` | Rogan-Gladen + two-sample bootstrap CI |
| `ppi_mean(y_lab, yhat_lab, yhat_unlab, *, weights, confidence)` | `correction` | Prediction-powered estimate (§13.3) |
| `mcnemar_exact(b, c)` | `compare` | Paired significance test (§13.4) |
| `paired_bootstrap(a, b, *, clusters, rng)` | `compare` | CI on the paired difference |
| `cluster_robust_se(scores, clusters)` | `clustered` | Correlated questions (§13.5) |
| `required_n_paired(p_disc, delta, alpha, power)` | `power` | "Need N more" (§13.6) |
| `ece(probs, y, n_bins)` / `brier(probs, y)` / `reliability_bins(...)` | `calibration` | Is the confidence honest? (§13.7) |
| `platt_fit` / `isotonic_fit` | `calibration` | Post-hoc recalibration, fitted on dev only |
| `ipw_weights(inclusion_prob)` | `weighting` | Unbiasedness under active sampling (§13.9) |

**Hard rules**

- Never report a point estimate without an interval.
- If the Rogan-Gladen denominator `sens + spec − 1 ≤ 0.1`, refuse to correct and say that the judge is too weak to use.
- Always report the `UNKNOWN` rate next to any estimate.

---

## 8. Judges: specification

### 8.1 Contract

- **Binary only:** `PASS` / `FAIL` / `UNKNOWN`. There are no Likert scales (see §13.10).
- **One criterion per judgment.** Several criteria per *call* is fine (`judge_many`), but each gets its own verdict.
- **`judge_id` is a content hash** of (adapter type, model, template text, template version, temperature and other params, few-shot example IDs). Changing any of these gives a new `judge_id`, which invalidates the cache and forces the judge to be re-validated.
- **Few-shot examples may come only from the `train` split.** The runner enforces this.

### 8.2 Getting a probability from an LLM judge

When the provider exposes token log-probabilities, ask for a **single-token answer** and read its distribution:

```
P(PASS) = exp(lp_PASS) / (exp(lp_PASS) + exp(lp_FAIL))
```

Pitfalls:

- A word like "PASS" may be split into several tokens. Use labels that are single tokens (e.g. `A`/`B` or `yes`/`no`) and verify this per model.
- Not every provider returns logprobs. Then `probability = None`, and the calibration metrics are skipped for that judge.
- There is a tension between *reasoning first* (usually more accurate) and a clean single-token verdict. Support two modes: `verdict_only` (logprobs) and `reason_then_verdict` (no probability).
- **Never ask the model to state its confidence in words.** That number is generated text, not a measurement.

### 8.3 Bias controls

| Bias | Control |
|---|---|
| Position (in pairwise mode) | Run both orders; keep the result only if both agree, otherwise mark `UNKNOWN` |
| Verbosity | Criteria phrased so they don't reward length; report the correlation between length and verdict |
| Self-preference | Warn when the judge's model family equals the target's model family |
| Anchoring (humans) | Blind labeling: the judge's verdict is hidden while a human labels |

### 8.4 Cascade

`CascadeJudge(cheap, strong, threshold)`:

- If `cheap.probability ≥ τ` or `≤ 1 − τ`, accept the cheap verdict.
- Otherwise, escalate to `strong`.

`τ` is chosen on **dev** to hit a target accuracy (or cost), and the cascade is evaluated on **test**. The `judge_id` of a cascade includes the IDs of both judges and `τ`.

---

## 9. Runner, caching and reliability

- **Concurrency:** `asyncio` plus a `Semaphore(max_concurrency)` for each provider.
- **Retries:** exponential backoff with jitter on 429 and 5xx responses, plus a per-call timeout. Non-retryable errors are recorded as failed jobs, not silently dropped.
- **Idempotency:** the primary key `(trace_id, criterion_id, judge_id)` means reruns are free and a crashed run resumes where it stopped.
- **Budget:** optional `max_cost_usd`. The runner stops scheduling new calls when the projected spend would exceed it.
- **Run manifest:** config snapshot, `judge_id`s, package version, git SHA and RNG seed, stored with each run so any figure can be reproduced.
- **Secrets:** API keys are read only from environment variables named in config (`api_key_env = "..."`). They are never written to the store or logs.
- **Privacy:** everything is local by default. An optional `redact` hook runs on traces before they're sent to any external judge.

---

## 10. Configuration and public API

### 10.1 `evalhawk.toml`

```toml
version = 1                              # config format version (a one-way door, see roadmap)

[project]
name  = "support-bot"
store = "sqlite:///.evalhawk/eval.db"    # keep on a local disk, not a synced folder

# The app under test. Pick ONE target type (§5.1).
[target]
type          = "http"
url           = "https://bot.internal/api/chat"
headers       = { Authorization = "Bearer ${BOT_API_KEY}" }   # expanded from the environment
body          = '{"message": "{{input}}"}'
answer_path   = "$.reply.text"
contexts_path = "$.reply.sources[*].text"                     # only for kind = "rag"
timeout       = 30
# type = "callable"; callable = "my_app.bot:answer"            # alternative: a Python function

[splits]
train = 0.2
dev   = 0.4
test  = 0.4
salt  = "v1"                            # changing the salt = a brand-new split
by    = "group_id"                      # keep related examples in the same pile

[[criteria]]
id       = "no_fabrication"
question = "Is every factual claim in the answer supported by the provided context?"

[evaluations.support_rag]
dataset   = "data/support_eval.jsonl"
kind      = "rag"                        # data shape checked at load time
criteria  = { no_fabrication = "cascade" }   # criterion -> judge
estimator = "ppi"                        # or "rogan_gladen"
repeats   = 1                            # >1: repeats are clustered by example

[judges.local]
type        = "openai_compatible"
base_url    = "http://localhost:11434/v1"   # Ollama
model       = "qwen3:8b"
mode        = "verdict_only"
api_key_env = "OLLAMA_API_KEY"
headers     = {}                         # extra HTTP headers (e.g. for a corporate gateway)
verify      = true                       # or a path to a CA bundle
timeout     = 60

[judges.jev]
type = "jev"

[judges.cascade]
type      = "cascade"
cheap     = "jev"
strong    = "local"
threshold = "auto"                       # chosen on the dev split

[runner]
max_concurrency = 8
max_cost_usd    = 2.00
seed            = 42
```

### 10.2 Python API

```python
import evalhawk as eh

project = eh.Project.from_config("evalhawk.toml")
run = await project.run(version="v2")
report = project.estimate(run, criterion="no_fabrication", judge="cascade")
print(report)  # 0.781 [0.742, 0.816] (rogan_gladen+bootstrap, n=412, unknown=1.2%)

cmp = project.compare(base="v1", candidate="v2", criterion="no_fabrication")
assert not cmp.significant_regression
```

---

## 11. Testing strategy

| Layer | What is tested | How |
|---|---|---|
| `stats/` unit | Known textbook values (Wilson, kappa, McNemar) | `pytest`, exact numbers from references |
| `stats/` property | Invariants: `low ≤ point ≤ high`; results don't depend on input order; CIs shrink as n grows; symmetry of paired tests | Hypothesis |
| **`stats/` validation** | **Coverage:** simulate a judge with known sens/spec at a known true rate θ; over 2,000 runs, the 95% CI contains θ between 93.5% and 96.5% of the time | Seeded simulation, marked `slow`, run nightly and before release |
| `stats/` oracle | PPI results match `ppi-python` within tolerance | Dev-only dependency |
| `core/` | Split determinism, immutability (the trigger fires), stable IDs | Unit + property |
| Integration | Full flow with a `FakeTarget` and `FakeJudge` (known error rates), no network | pytest + temporary SQLite |
| Adapters | Request/response mapping | Recorded HTTP fixtures (no live calls in CI) |
| UI | Routes return the right partials; the labeling flow round-trips | FastAPI `TestClient` |

CI runs everything except `slow` and live-API tests on every push.

---

## 12. Plan of action (technical, per phase)

Timeline and "done when" criteria are in the [roadmap](roadmap.md). The build order of these phases is set by the stages in [ADR-0007](decisions/0007-build-order.md). This section lists the **files, functions and tests** for each phase, in build order.

### Phase 0: Foundation
- `pyproject.toml` (hatchling, `requires-python = ">=3.11"`, extras declared empty), `.pre-commit-config.yaml`, `ci.yml` (matrix across py3.11–3.13 on ubuntu and windows).
- Ruff rules: `E, W, F, I, B, UP, SIM, N, PT, RUF`. Pyright `strict` for `src/evalhawk/core` and `src/evalhawk/stats`.
- ADRs 0001–0008, requirements, standards, design patterns, limitations.
- `import-linter` contracts for the layer rules.

### Phase 1: Core models and interfaces
1. `core/ids.py`: `content_id(obj) -> str`, using canonical JSON (sorted keys, no whitespace) then sha256.
2. `core/models.py`: Pydantic models from §4.1; `frozen=True` where possible.
3. `core/protocols.py`: §5.
4. `core/splits.py`: `assign_split(key, salt, ratios) -> Split`, where `u = int(sha256(salt + key)[:8], 16) / 16**8`, mapped onto cumulative ratios. The key is `group_id` when set, otherwise `example_id`.
5. `storage/sqlite.py` + `0001_init.sql`: §4.2, WAL, `busy_timeout`, migration runner.
6. `sources/jsonl.py`, `sources/csv.py`.
- **Tests:** stable IDs; same key → same split; the trigger blocks UPDATE and DELETE; JSONL round-trip.

### Phase 2: Statistics core
Build in this order, because each step uses the previous one:
1. `intervals.wilson_interval`, `intervals.bootstrap_ci`
2. `agreement.confusion`, `tpr_tnr`, `cohen_kappa`
3. `correction.rogan_gladen`, `correction.corrected_pass_rate` (two-sample bootstrap)
4. `correction.ppi_mean`
5. `compare.mcnemar_exact`, `compare.paired_bootstrap`
6. `clustered.cluster_robust_se` (+ `clusters=` support in the bootstrap)
7. `power.required_n_paired`
8. `calibration.*`, `weighting.ipw_weights`
- **Tests:** §11 rows 1–4. The coverage simulation is the phase gate.
- **Figure:** `experiments/scripts/coverage_naive_vs_corrected.py`.

### Phase 3: Judges, runner, CLI
1. `judges/base.py`: the optional `PromptJudge` helper: template rendering, strict output parsing (`PASS`/`FAIL`/`UNKNOWN`), `judge_id` derivation (LF-normalised template text).
2. `judges/openai_compat.py`: both modes (§8.2); options `headers`, `verify`, `timeout`; lazy import of `openai`.
3. `judges/function.py`, `judges/cached.py`.
4. `targets/`: `callable.py`, `recorded.py`, `http.py`, `openai_compat.py` (§5.1).
5. `runner/executor.py`, `runner/cache.py`, `runner/budget.py`; `repeats` and `--sample N`.
6. `config.py` (TOML → Pydantic, `${ENV}` expansion), `plugins.py`, `wiring.py` (composition root).
7. `services/calibrate.py` (agreement + `Calibration` records with status), `services/estimate.py`, `services/evaluate.py`, `services/export.py`.
8. `cli/`: `init`, `import`, `eval`, `report`, `export`, `judges status`, `judges compare`.
9. Switch on import-linter contracts 2 and 3 once `services/`, `runner/` and the adapters exist.
10. `experiments/datasets/mtbench_human.py`, `llmbar.py`: convert to Examples, Traces and Labels.
- **Tests:** a fake judge with a known error rate gives the expected sensitivity within its CI; a rerun makes zero API calls (cache); retries on a mocked 429; secrets never appear in the store or logs.

### Phase 4: Labeling UI
1. `ui/app.py` (app factory), `routes/label.py` (GET next item, POST label → returns the next item as an htmx partial).
2. Keyboard shortcuts: `hx-trigger="keyup[key=='p'] from:body"` and similar for `f`, `u`, `→`.
3. Queue strategies in `services/label_queue.py`; `inclusion_prob` is written with every label.
4. `routes/report.py`: agreement table + reliability chart (uPlot, vendored).
5. `routes/criteria.py`: create or version criteria while labeling.
- **Tests:** `TestClient` flow; the rendered label page never contains the verdict (asserted in a test).

### Phase 5: JEV and cascades
1. `judges/jev.py`: implements `MultiCriterionJudge`; always includes an "unknown" option; one fixed question format.
2. `calibration.platt_fit` / `isotonic_fit` wired into a `RecalibratedJudge` wrapper.
3. `judges/cascade.py`, `services/cascade_eval.py`: sweep `τ` on dev, produce a cost-vs-accuracy curve, pick `τ`, evaluate on test.
4. `services/error_correlation.py`: P(strong wrong | cheap wrong) vs P(strong wrong), with CIs.
5. `experiments/scripts/jev_study.py` + `Makefile`.

### Phase 6: Compare and CI gate
1. `services/compare.py`: pairing on `example_id`; returns a `Comparison` with the decision and `need_n`.
2. `cli compare` with exit codes 0/1/2.
3. A composite GitHub Action (`action.yml`) and an example workflow in `examples/`.

### Phase 7: Failure discovery
1. `clustering/embed.py` (an `Embedder` protocol + fastembed default), `cluster.py` (sklearn `HDBSCAN` on L2-normalised vectors; label `-1` means noise).
2. `naming.py`: the LLM proposes a name and a draft criterion question per cluster; the human accepts or edits it in the UI; it becomes a new `Criterion`.

### Phase 8: RAG
1. `rag/retrieval_metrics.py`: recall@k, MRR, nDCG (§13.12).
2. `rag/criteria.py`: templates for faithfulness, answer relevance and context relevance, using `Trace.contexts`.
3. `experiments/datasets/ragtruth.py` + a comparison against Ragas on the same traces.

### Phase 9: Launch
1. Docs polish on the existing Zensical site; `examples/01–03`.
2. `release.yml`: build → publish with PyPI trusted publishing (OIDC).
3. `sources/langfuse.py`, `sources/otel.py`.

---

## 13. Concepts you must know

Each concept below lists what it is, why it matters here, the formula where there is one, and the usual pitfall.

### 13.1 Confusion matrix, TPR/TNR, Cohen's kappa

Treat the human label as the truth and the judge as a classifier. **In this project, "positive" means PASS.**

| | Human PASS | Human FAIL |
|---|---|---|
| **Judge PASS** | TP | FP |
| **Judge FAIL** | FN | TN |

- **Sensitivity** `s = TP / (TP + FN)`: of the truly good outputs, the share the judge passes.
- **Specificity** `c = TN / (TN + FP)`: of the truly bad outputs, the share the judge catches.
- **Cohen's kappa** `κ = (p_o − p_e) / (1 − p_e)`: agreement corrected for chance. `p_o` is observed agreement; `p_e = P_h(PASS)·P_j(PASS) + P_h(FAIL)·P_j(FAIL)`.

**Pitfall.** Raw accuracy hides a lazy judge. If 95% of outputs pass, a judge that always says PASS gets 95% accuracy and specificity 0. Always report `s` and `c` separately.

**Naming trap.** Hamel Husain's material treats *failure* as the positive class, so his "TPR" is our specificity. Pick one convention and label outputs explicitly.

### 13.2 Confidence intervals for a proportion

- **Wald** (`p̂ ± z·√(p̂(1−p̂)/n)`) is badly wrong for small `n` or `p̂` near 0 or 1. **Don't use it.**
- **Wilson** (use this):
  `center = (p̂ + z²/2n) / (1 + z²/n)`
  `half   = z/(1 + z²/n) · √( p̂(1−p̂)/n + z²/4n² )`
- **Percentile bootstrap:** resample with replacement, recompute the statistic, and take the 2.5th and 97.5th percentiles. It is general-purpose and works for statistics that have no formula.

**Pitfall.** A CI is a statement about the *procedure*: "95% of intervals built this way contain the truth." Your simulation test checks exactly this property.

### 13.3 Correcting a biased judge

**The estimand.** We want θ, the pass rate *as a human would judge it*, over the population of inputs. The judge only gives us `q`, the judge's pass rate.

**Rogan-Gladen.** If the judge's error rates don't depend on the input (given the true label):

```
q = s·θ + (1 − c)·(1 − θ)      ⇒      θ = (q + c − 1) / (s + c − 1)
```

Estimate `s` and `c` on the labeled calibration set and `q` on the large unlabeled set, then clip θ to [0, 1]. For the CI, **bootstrap both sets independently**, so the uncertainty in `s` and `c` is included.

- It needs `s + c > 1` (the judge is better than random). As `s + c − 1 → 0`, the estimate blows up. That is why §7 has a refusal rule.
- Assumption: the judge's error rates are the same on the calibration set and the test set.

**Prediction-powered inference (PPI).** Use a small labeled set `(Xⱼ, Yⱼ)` with n items and a large unlabeled set with N items. `f` is the judge (a 0/1 verdict or a probability).

```
θ̂_PP = mean_N( f(X̃) )  −  mean_n( f(X) − Y )
                             └── "rectifier": the judge's average error
Var ≈ Var(f(X̃))/N + Var(f(X) − Y)/n
```

- It's unbiased whatever the judge's quality. A good judge simply makes the interval narrower.
- **PPI++** adds a tuning weight λ so PPI is never worse than using the human labels alone.
- Assumption: the labeled set is a **random sample** from the same distribution. If the labeling queue is not random, you need IPW weights (§13.9).

**Know the trade-off.** Rogan-Gladen relies on stable judge error rates; PPI relies on a representative labeled set. Implement both and compare them in the Phase 5 study.

### 13.4 Paired comparison (v1 vs v2)

Both versions answer the *same* inputs. Only the inputs where they **disagree** carry information:

| | v2 PASS | v2 FAIL |
|---|---|---|
| **v1 PASS** | – | b |
| **v1 FAIL** | c | – |

- **Exact McNemar:** under "no difference", `b ~ Binomial(b + c, 0.5)`. The p-value is a two-sided binomial test.
- **Paired bootstrap:** resample *example IDs* (not traces) and recompute `mean(v2) − mean(v1)`.

**Why pairing matters.** Many inputs are easy (both pass) or hard (both fail). Pairing cancels that shared difficulty, so paired tests detect smaller differences with the same data.

**Pitfall.** Running v1 and v2 on different random samples and comparing their CIs throws away that power.

### 13.5 Clustered standard errors

If questions come in related groups (same document, same user, several questions from one source), they aren't independent, and the usual standard error is **too small** (Anthropic reports up to about 3× on real benchmarks).

Cluster-robust variance of a mean score `x̄` over clusters `g`:

```
Var(x̄) = (1/n²) · Σ_g ( Σ_{i ∈ g} (sᵢ − x̄) )²
```

Equivalently, use a **cluster bootstrap**: resample whole clusters, not individual items. Splits must also be group-aware (§4.1), so a group never spans train and test.

### 13.6 Power and sample size

"Do I have enough examples to detect a Δ-point change?" For a paired design, each example contributes `dᵢ ∈ {−1, 0, +1}`:

```
Var(d) = p_disc − Δ²                              (p_disc = share of discordant pairs)
n ≈ (z_{1−α/2} + z_{1−β})² · (p_disc − Δ²) / Δ²
```

With α = 0.05 and 80% power, `(1.96 + 0.84)² ≈ 7.85`. Estimate `p_disc` from a pilot run and report "need ≈ N more examples".

**Pitfall.** A non-significant result with a small `n` means "we can't tell yet", not "no difference". The `INCONCLUSIVE` verdict exists for this reason.

### 13.7 Probability calibration

A judge is **calibrated** when outputs it scores 0.8 are correct about 80% of the time.

- **Reliability diagram:** bin predictions by confidence and plot accuracy against mean confidence per bin.
- **ECE:** `Σ_b (n_b / N) · | acc_b − conf_b |`. It's simple but depends on how you bin, so report the bin count.
- **Brier score:** `mean( (p − y)² )`. A proper scoring rule, so it rewards both calibration and sharpness.
- **Recalibration:** Platt scaling (logistic regression on the logit) or isotonic regression. **Fit on dev and evaluate on test.**

**Pitfall.** Good accuracy does not imply good calibration, and the reverse is also true. The JEV audit showed confidence collapsing when the "unknown" option was removed.

### 13.8 Selective prediction and cascades

- **Coverage:** the share of items the cheap judge decides itself. **Selective risk:** its error rate on those items.
- Sweeping `τ` traces a risk–coverage curve. Pick `τ` on dev and report on test.
- **Error correlation:** a cascade only helps if the strong judge is right where the cheap one is wrong. Compare `P(strong wrong | cheap wrong)` with `P(strong wrong)`. If these are close to each other, errors are independent and escalation helps; if the conditional is much higher, it doesn't. The "Wrong in the Same Places" paper found 96% vs about 50%.

### 13.9 Active sampling without bias: inverse-probability weighting

Labeling "uncertain first" makes the labeled set unrepresentative, which silently biases every estimate. The fix is the **Horvitz-Thompson / IPW** estimator: record each item's selection probability `πᵢ` and weight it by `1/πᵢ`:

```
θ̂ = Σ (yᵢ / πᵢ) / Σ (1 / πᵢ)
```

Rule: every selection probability must be **greater than 0** (keep a small random component in the queue), or the estimator is undefined for items that could never be picked.

### 13.10 Eval methodology (qualitative, but required)

- **Error analysis first:** read about 100 traces, write free-text notes (open coding), then group them into failure modes (axial coding). Criteria come *from* this step.
- **Criteria drift:** people refine what "good" means while they label (Shankar et al., EvalGen). Hence versioned criteria.
- **Binary over Likert:** 1–5 scales produce inconsistent labels and cluster in the middle. Binary questions force a decision.
- **One judge per failure mode:** a judge asked to catch everything catches nothing reliably.

### 13.11 Data leakage and overfitting the judge

- Judge prompts are tuned on **dev**; few-shot examples come from **train**; **test** is read once.
- Tuning the judge until it agrees with you on the test set turns the test set into a second dev set. The `test_access_log` makes this visible.
- Splits are **deterministic and immutable** (hash-based plus the DB triggers).

### 13.12 RAG metrics

With `rel(i) ∈ {0, 1}` meaning the result at rank i is relevant:

- **Recall@k** = relevant documents in the top k ÷ all relevant documents.
- **MRR** = mean over queries of `1 / rank of the first relevant document`.
- **nDCG@k** = `DCG@k / IDCG@k`, where `DCG@k = Σᵢ₌₁ᵏ rel(i) / log₂(i + 1)`.
- **Faithfulness:** is every claim in the answer supported by the retrieved context? This is an LLM or JEV judgment, not a string-overlap metric.
- **Context relevance vs answer relevance:** they identify different failures (bad retrieval vs bad generation). Keep them as separate criteria.

### 13.13 LLM-judge biases

Position, verbosity, self-preference and sensitivity to prompt format. Know the controls in §8.3, and always record the `judge_id`, so any bias you find can be traced to one exact configuration.

### 13.14 Engineering concepts

| Concept | Where it's used |
|---|---|
| **Structural typing** (`typing.Protocol`) | Every plug-in point; users implement interfaces without importing a base class |
| **Dependency injection** | Config builds the adapters and passes them in; nothing below `cli/` constructs a vendor client |
| **Content-addressed IDs** | Stable example, trace and judge IDs; cache keys; reproducibility |
| **Idempotency** | Verdict primary key → reruns are safe and free |
| **asyncio** (`Semaphore`, `gather`, timeouts) | Runner fan-out with per-provider limits |
| **Exponential backoff with jitter** | 429 and 5xx handling |
| **SQLite WAL, `busy_timeout`, transactions, triggers** | Safe CLI + UI concurrency; immutable splits |
| **Optional dependencies + lazy imports** | Small core install; `import evalhawk` never fails |
| **Entry points** | Third-party plugins |
| **htmx model** (server returns HTML partials) | A labeling UI without a JavaScript build |
| **Trusted publishing (OIDC)** | Releasing to PyPI without stored tokens |
| **OpenTelemetry GenAI semantic conventions** | Naming trace fields so importers are easy (the spec is still experimental; check the current version) |

---

## 14. Reading list

**Methodology**
- Hamel Husain: [AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/) and [Using LLM-as-a-Judge](https://hamel.dev/blog/posts/llm-judge/)
- Shankar et al.: [Who Validates the Validators? (EvalGen)](https://arxiv.org/abs/2404.12272)
- Zheng et al.: [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)
- [LLMs-as-Judges: A Comprehensive Survey](https://arxiv.org/abs/2412.05579)

**Statistics**
- Miller (Anthropic): [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640)
- Angelopoulos et al.: [Prediction-Powered Inference](https://arxiv.org/abs/2301.09633) · [ppi_py](https://github.com/aangelopoulos/ppi_py)
- [How to Correctly Report LLM-as-a-Judge Evaluations](https://arxiv.org/abs/2511.21140)

**JEV**
- [JEV-as-a-Judge: Accept When Confident, Escalate When Unsure](https://arxiv.org/abs/2609.26550)
- [Cheaper, Faster, and Wrong in the Same Places](https://arxiv.org/html/2609.29769)
- [jev-calibration-audit](https://github.com/jujumilk3/jev-calibration-audit)

**Datasets for validation**
- MT-Bench human judgments · [LLMBar](https://arxiv.org/abs/2310.07641) · [JudgeBench](https://arxiv.org/abs/2410.12784) · RAGTruth

**Engineering**
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/blog/2026/genai-observability/)
- [htmx docs](https://htmx.org/docs/) · [FastAPI docs](https://fastapi.tiangolo.com/) · [uv docs](https://docs.astral.sh/uv/)
