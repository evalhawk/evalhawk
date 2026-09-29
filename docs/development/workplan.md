# Work plan: stages B–D

Who builds what, in which order, and what "done" means for each task. Every card below
becomes a GitHub issue. Each card is self-contained, so you can hand it to Claude Code as-is.

**Working rules:** the [maintainer agreement](collaboration.md) and the
[engineering standards](standards.md). **Definition of done** for every card: tests pass,
ruff, pyright and import-linter pass, docstrings written, the other maintainer approved the
PR, and a [dev-log](../devlog/index.md) entry is written.

## The big picture

```
                     ┌──────────────────────┐
  Week 1             │ J1  Shared contract  │   (pair: both of you)
                     │ core/results.py      │
                     └──────────┬───────────┘
                ┌───────────────┴────────────────┐
                ▼                                ▼
   TRACK 1: STATISTICS ENGINE       TRACK 2: DATA BACKBONE
   Owner: Karthik                   Owner: Krishna
   S1 Wilson interval               D1 Content IDs         ← D1 can start
   S2 Judge agreement               D2 Data models            before J1
   S3 Judge correction (RG)         D3 Split assignment
   S4 v1 vs v2 comparison           D4 Protocols
   S5 PPI correction                D5 SQLite store
   S6 Clustered errors + power      D6 JSONL / CSV import
   S7 ⭐ Coverage simulation        D7 ⭐ Fakes for testing
                └───────────────┬────────────────┘
                                ▼
                 STAGE D: SWAP (each works in the other's world)
                 X1 Krishna: store → stats glue (services/estimate.py)
                 X2 Karthik: import recorded verdicts + DeepEval results
                 X3 Pair:    `evalhawk import` + `evalhawk report`   ← first demo
```

- The tracks **don't block each other**: `stats/` takes NumPy arrays and never touches models
  or the database.
- The only shared piece is **J1**. Track 1 needs it before S1; Track 2 doesn't need it until
  much later, so Krishna can start D1 on day one.
- To swap tracks, change the owner names on this page in a PR. Both of you approve.

## How to start any card with Claude Code

> Read `CLAUDE.md` and card **S1** in `docs/development/workplan.md`. First explain the
> concept to me simply, with an example. Then help me write the tests, and only then the
> code. Don't commit or push.

---

## J1 · Shared contract: `Estimate` and errors

**Owner:** both (pair) · **Depends on:** nothing · **Files:** `src/evalhawk/core/results.py`, `src/evalhawk/core/errors.py`

**Learn:** value objects, frozen dataclasses, designing an interface two people depend on.

**Build:**

- `Estimate`: a frozen dataclass (`slots=True`) with `point`, `low`, `high`, `n`, `method`,
  `confidence` (default 0.95) and `unknown_rate` (default 0.0). Validated in `__post_init__`;
  `width` property; readable `__str__` such as `0.820 [0.733, 0.883] (wilson, n=100, unknown=0.0%)`.
- `errors.py`: `EvalhawkError`, plus `DataError`, `ConfigError`, `StoreError`.

**Decide together** (and write the answer in the docstring): percentile bootstrap intervals
can, rarely, fail to contain the point estimate. Should `Estimate` reject that, or only
require `low ≤ high`?

**Done when:**

- Invalid values raise `ValueError` (e.g. `low > high`, `n < 0`, `confidence` outside (0, 1))
- `Estimate` can't be modified after creation (test it)
- `__str__` output is tested exactly
- pyright strict passes

---

## Track 1: statistics engine (owner: Karthik)

All functions live in `src/evalhawk/stats/`, are **pure** (arrays in, `Estimate` out), take
randomness as `rng: np.random.Generator`, and use **NumPy and the standard library only**.
SciPy may be used **in tests** as a reference (pending [ADR-0009](../decisions/0009-lean-runtime-no-scipy.md)).

### S1 · Wilson interval

**Depends on:** J1 · **File:** `stats/intervals.py`

**Learn:** confidence intervals for a proportion; why the simple "Wald" formula fails for
small samples.

**Build:** `wilson_interval(k: int, n: int, *, confidence: float = 0.95) -> Estimate`.
Use `statistics.NormalDist().inv_cdf` for the z-value.

**Done when (unit tests with these exact values, 4 decimals):**

| k | n | low | high |
|---|---|---|---|
| 82 | 100 | 0.7333 | 0.8830 |
| 0 | 10 | 0.0000 | 0.2775 |
| 10 | 10 | 0.7225 | 1.0000 |
| 500 | 1000 | 0.4691 | 0.5309 |

- `n = 0`, `k < 0` or `k > n` raise `ValueError`
- Property tests (Hypothesis): `0 ≤ low ≤ point ≤ high ≤ 1`; symmetric (`k` and `n−k`
  mirror each other); the interval narrows as `n` grows at a fixed rate

**Read:** Wikipedia, *Binomial proportion confidence interval* (Wilson section); Brown, Cai & DasGupta (2001), pass 1.

### S2 · Judge agreement

**Depends on:** S1 · **File:** `stats/agreement.py`

**Learn:** confusion matrices; sensitivity and specificity; why raw agreement misleads;
Cohen's kappa. (Remember: in EvalHawk **PASS is the positive class**.)

**Build:**

- `confusion(human, judge) -> Confusion` (counts `tp, fn, fp, tn` from two 0/1 arrays)
- `sensitivity(c) -> Estimate`, `specificity(c) -> Estimate` (Wilson intervals)
- `cohen_kappa(human, judge, *, rng, n_boot=2000) -> Estimate` (bootstrap interval)

**Done when:** a hand-computed example matches; mismatched lengths or non-0/1 values raise
`ValueError`; a judge that always says PASS gets specificity 0; a kappa property test: a perfect
judge gives kappa = 1.

**Read:** Wikipedia, *Sensitivity and specificity* and *Cohen's kappa*; Hamel Husain, *Using LLM-as-a-Judge*.

### S3 · Judge correction (Rogan-Gladen)

**Depends on:** S2 · **File:** `stats/correction.py`

**Learn:** correcting a measured rate for a known error rate; bootstrap intervals;
the fast **count-based** bootstrap (resample counts, not rows).

**Build:**

- `rogan_gladen(q, sensitivity, specificity) -> float`: `(q + c − 1) / (s + c − 1)`, clipped to [0, 1]
- `corrected_pass_rate(judge_test, judge_cal, human_cal, *, rng, n_boot=2000) -> Estimate`:
  a two-sample bootstrap that uses `rng.multinomial` for the four calibration cells and
  `rng.binomial` for the test pass count
- Refuse when `s + c − 1 ≤ 0.1`: raise a new `JudgeTooWeakError(EvalhawkError)` whose
  message explains why

**Done when:** `rogan_gladen(0.82, 0.95, 0.60)` = **0.7636**; the refusal is tested;
2,000 resamples on 100k test items take under 50 ms (a benchmark test, marked `slow`).

**Read:** architecture §13.3; *How to Correctly Report LLM-as-a-Judge Evaluations* (arXiv 2511.21140), method section.

### S4 · Version comparison (v1 vs v2)

**Depends on:** S1 · **File:** `stats/compare.py` (+ `Comparison` in `core/results.py`)

**Learn:** paired designs; McNemar's test; why only disagreements matter.

**Build:**

- `mcnemar_exact(b, c) -> float`: the log-space algorithm (see the benchmark in the
  2026-09-28 design discussion). No SciPy, no big integers.
- `paired_bootstrap(a, b, *, rng, n_boot=2000) -> Estimate`: interval on `mean(b) − mean(a)`,
  resampling **example indices**
- `Comparison` value object and `decide(diff) -> "BETTER" | "WORSE" | "INCONCLUSIVE"`

**Done when:** `mcnemar_exact(12, 30)` ≈ **0.00792**; matches `scipy.stats.binomtest` to a
relative error below 1e-9 on 5,000 random cases (a test-only SciPy check); `b = c` gives 1.0.

**Read:** Wikipedia, *McNemar's test*; Miller (2024), section on paired differences.

### S5 · PPI correction

**Depends on:** S1 · **File:** `stats/correction.py`

**Learn:** prediction-powered inference: correcting with the judge's average error
measured on labeled data.

**Build:** `ppi_mean(y_labeled, yhat_labeled, yhat_unlabeled, *, confidence=0.95) -> Estimate`
(classical PPI with a normal-approximation interval).

**Done when:** matches the `ppi-python` reference implementation within 1e-6 on fixed data
(`ppi-python` added as a **dev-only** dependency; check its current version first).

**Read:** Angelopoulos et al. (2023), pass 1; the mean-estimation example in the `ppi_py` repo.

### S6 · Clustered errors and "need N more"

**Depends on:** S1, S4 · **Files:** `stats/clustered.py`, `stats/power.py`

**Learn:** why related questions widen error bars; how sample size is planned.

**Build:**

- `cluster_robust_se(scores, clusters) -> float` and a `clusters=` option for the bootstraps
  (resample whole clusters)
- `required_n_paired(p_discordant, delta, *, alpha=0.05, power=0.8) -> int`

**Done when:** with every item in its own cluster, the clustered SE equals the ordinary SE;
with duplicated clusters the SE grows; the power formula reproduces a hand-computed example.

**Read:** Miller (2024), clustered standard errors and power analysis.

### S7 · ⭐ Coverage simulation (the proof)

**Depends on:** S1–S6 · **Files:** `tests/validation/test_coverage.py`, `experiments/scripts/coverage_naive_vs_corrected.py`

**Learn:** what a confidence interval promises, and how to test that promise.

**Build:** simulate a judge with known sensitivity and specificity at a known true pass
rate. Over 2,000 runs, check how often each method's 95% interval contains the truth:
naive, Rogan-Gladen, PPI, and clustered. Produce a chart of naive vs corrected coverage.

**Done when:** corrected methods cover **93.5%–96.5%**; the naive method visibly fails;
tests are marked `slow`; the chart is saved to `experiments/figures/`. This is the first
portfolio artefact.

---

## Track 2: data backbone (owner: Krishna)

Files live in `src/evalhawk/core/`, `storage/`, `sources/` and `testing/`. `core/` must stay
pure: no I/O, no vendor SDKs (import-linter enforces this).

### D1 · Content IDs

**Depends on:** nothing (start here) · **File:** `core/ids.py`

**Learn:** hashing; canonical JSON; content addressing; why this is a one-way door.

**Build:** `content_id(obj) -> str`: SHA-256 hex of canonical JSON (UTF-8, sorted keys,
`separators=(",", ":")`, NaN and Infinity rejected). Plus `normalize_text(s)`, which converts
CRLF/CR line endings to LF (used for prompt templates).

**Done when:**

- **Golden tests** pin the exact hash of three fixed objects. These must never change
  ([ADR-0006](../decisions/0006-content-addressed-ids-and-splits.md)).
- Property test: key order doesn't change the ID
- NaN raises `ValueError`

**Read:** ADR-0006; Python `json` and `hashlib` docs.

### D2 · Data models

**Depends on:** D1 · **File:** `core/models.py`

**Learn:** Pydantic v2; immutable domain models; validation at the boundary.

**Build:** `Outcome` (PASS, FAIL, UNKNOWN) and `Split` (train, dev, test) enums; frozen
Pydantic models `Example`, `Run`, `Trace`, `Criterion`, `Verdict`, `Label`, `Evaluation`,
`Calibration` with the fields in architecture §4.1. IDs are computed with `content_id`, and
`extra="forbid"`.

**Done when:** each model's ID is stable (golden test); unknown fields are rejected; models
can't be modified; an `Evaluation` of kind `rag` rejects data without `contexts`, with a
message naming the field.

**Read:** architecture §4.1; the Pydantic docs, "Models".

### D3 · Split assignment

**Depends on:** D1 · **File:** `core/splits.py`

**Learn:** deterministic hashing into buckets; group-aware splitting; why test-set
leakage matters.

**Build:** `assign_split(key, *, salt, ratios=(0.2, 0.4, 0.4)) -> Split`, using
`u = int(sha256(salt + key)[:8], 16) / 16**8` mapped onto the cumulative ratios. The key is
`group_id` if set, else `example_id`.

**Done when:** golden tests pin the splits of fixed keys; 10,000 random keys land within
±2 points of each ratio; the same `group_id` always gives the same split; ratios that don't
sum to 1 raise `ValueError`.

**Read:** ADR-0006; architecture §13.11; Hamel Husain's FAQ on train/dev/test.

### D4 · Protocols (the plug-in contracts)

**Depends on:** D2 · **File:** `core/protocols.py`

**Learn:** structural typing with `typing.Protocol`; designing plug-in points.

**Build:** `Judge`, `MultiCriterionJudge`, `Target`, `TraceSource`, `Store`, following
architecture §5 and [ADR-0004](../decisions/0004-protocols-and-helper-base-classes.md).

**Done when:** a tiny test class satisfies each protocol without inheriting from anything
(checked by pyright and by `isinstance` for the `runtime_checkable` ones).

**Read:** PEP 544; *Architecture Patterns with Python*, chapters 1–2.

### D5 · SQLite store

**Depends on:** D2, D3, D4 · **Files:** `storage/sqlite.py`, `storage/migrations/0001_init.sql`

**Learn:** SQLite WAL, transactions, triggers, migrations; the repository pattern.

**Build:** `SQLiteStore` implementing `Store`:

- On connect: `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, `foreign_keys=ON`
- A migration runner based on `PRAGMA user_version` (forward only, one transaction each)
- The schema from architecture §4.2, including the **split-immutability triggers** and `test_access_log`
- Batched inserts with `executemany` inside one transaction
- Switch on import-linter **contract 3** (adapters) in `pyproject.toml`

**Done when:** a test proves an `UPDATE` or `DELETE` on `splits` is refused; data
round-trips; re-inserting the same example creates no duplicate; two connections can read
while one writes; 20,000 inserts take under 1 s.

**Read:** ADR-0001; SQLite docs on WAL and `CREATE TRIGGER`; Python `sqlite3` docs.

### D6 · JSONL and CSV import

**Depends on:** D2 · **Files:** `sources/jsonl.py`, `sources/csv.py`

**Learn:** streaming with iterators (constant memory); error messages users can act on.

**Build:** `JSONLSource(path)` and `CSVSource(path)` implementing `TraceSource`, yielding
`(Example, Trace | None)` one row at a time.

**Done when:** a bad row raises `DataError` naming the **file, row number and field**; a
100k-row file imports without loading everything into memory; blank lines are skipped.

### D7 · ⭐ Fakes for testing

**Depends on:** D4 · **File:** `src/evalhawk/testing/fakes.py`

**Learn:** test doubles; simulation with known ground truth; async code.

**Build:**

- `FakeJudge(sensitivity, specificity, *, rng)`: returns PASS/FAIL with **exactly known**
  error rates against the truth stored on the trace
- `FakeTarget`: returns canned outputs
- `InMemoryStore`: a dict-based `Store`, which proves the protocol is implementable without SQL

**Done when:** over 10,000 traces, the fake judge's measured sensitivity is within ±1 point
of its setting; `InMemoryStore` passes the same round-trip tests as `SQLiteStore`
(a shared test suite run against both).

---

## Stage D: swap and first demo

| Card | Owner | What | Why this owner |
|---|---|---|---|
| **X1** | Krishna | `services/estimate.py`: load arrays from the Store, call `stats`, return an `Estimate`. Switch on import-linter contract 2 | Krishna learns the statistics API |
| **X2** | Karthik | `sources/verdicts.py`: import recorded judge verdicts and human labels (JSONL, and DeepEval result files: score ≥ threshold → PASS) | Karthik learns the data layer |
| **X3** | Pair | `evalhawk import` and `evalhawk report` (Rich table): corrected pass rate, error range, judge report card | The first end-to-end demo, with zero LLM calls |

**Stage D is done when:** on a public dataset with human labels, `evalhawk report` prints a
judge report card and a corrected pass rate with an error range.

## Suggested first week

| | Karthik | Krishna |
|---|---|---|
| Day 1 | Phase 0 wrap-up: repo, settings, PyPI | Accept the org invite as Owner, clone, set up, first PR (approve the agreement + ADRs 0007, 0009) |
| Day 2 | **J1 together** | **J1 together** |
| Days 3–7 | S1 → S2 | D1 → D2 |
