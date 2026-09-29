# Roadmap

> **One-line pitch:** Bring your own model, judge and data. We make the eval numbers trustworthy.

A judge-agnostic evaluation tool for LLM apps. It checks whether an LLM judge (including cheap judges like JEV) can be trusted against human labels, corrects its bias, and reports every result with honest error bars.

This page covers **when** (phases and milestones). [Architecture](architecture.md) covers **how**, [Requirements](requirements.md) covers **what**, and the [decision records](decisions/index.md) cover **why**.

---

## 1. Principles

1. **Thin at the edges, thick in the middle.**
   - *Pluggable (thin):* the user's app, judge model, trace source, embeddings, storage backend.
   - *Fixed (thick):* the statistics, blind labeling, locked train/dev/test splits. This part is the product.
2. **Their data stays where it is.** We import traces. We only store our own state: labels, verdicts, results.
3. **One good default per interface.** Add more adapters only when a real user asks.
4. **Math before AI.** The stats core is built and proven before any LLM is called.
5. **Every phase ends in something that works and can be shown.**

## 2. Architecture (ports and adapters)

```
        ┌──────────── EDGES (pluggable) ─────────────┐
        │                                            │
 TraceSource ──┐                          ┌── Judge (OpenAI-compatible, JEV,
 (JSONL, CSV,  │     ┌───────────────┐    │    local, any Python function)
  Langfuse,    ├───► │  CORE (fixed) │ ◄──┤
  OTel)        │     │  - models     │    └── Target (the user's app: a callable
               │     │  - stats      │         or pre-recorded outputs)
 Store ────────┘     │  - splits     │
 (SQLite default)    │  - labeling   │
                     └──────┬────────┘
                            │
                 CLI  ·  Labeling UI  ·  CI gate
```

Core interfaces (Python `Protocol`s): `Judge`, `TraceSource`, `Store`, `Target`.

## 3. Tech stack

**Core install (kept tiny):** Python 3.11+ (develop on 3.12) · Pydantic v2 · NumPy · SciPy · Typer (includes Rich) · `sqlite3` (standard library) · TOML config via `tomllib` (standard library)

**Optional extras:**

| Extra | Packages | Purpose |
|---|---|---|
| `[llm]` | `openai` | Any OpenAI-compatible judge: OpenAI, Ollama, Groq, Gemini, OpenRouter |
| `[jev]` | `typesafe-sdk` | JEV judge |
| `[ui]` | `fastapi`, `uvicorn`, `jinja2` (+ bundled htmx 2, uPlot) | Labeling screen and reports |
| `[cluster]` | `fastembed`, `scikit-learn` | Failure clustering (ONNX, no torch) |
| `[langfuse]`, `[otel]` | adapters | Import traces |

**Dev only:** uv · hatchling · pytest · hypothesis · ruff · pyright · import-linter (layer rules) · pre-commit · GitHub Actions · Zensical (docs site, [ADR-0008](decisions/0008-zensical-docs.md)) · `ppi-python` (reference implementation to check our math against)

**Free compute:** Ollama (local) · Groq / Google AI Studio free tiers. Google's free tier may use submitted data, so don't send private data through it.

---

## 4. Build order: stages

*Proposed in [ADR-0007](decisions/0007-build-order.md), awaiting confirmation.* The phases below are grouped by topic. The **stages** are the order we build them in, so that every stage ends in something a person can use, and the riskiest part (the statistics) comes first.

| Stage | Name | Usable result | Phase |
|---|---|---|---|
| A | Foundation | Green CI | 0 |
| B | Calculator | `evalhawk.stats` gives a corrected pass rate with a CI from arrays | 2 |
| C | Memory | Models, IDs, splits, SQLite store, JSONL/CSV import | 1 |
| D | Offline report | `evalhawk import` + `evalhawk report` on pre-recorded verdicts and labels (zero LLM calls) | slice of 3 |
| E | Live judge | `evalhawk eval`: judges, runner, cache, targets | rest of 3 |
| F | Labeling | Blind labeling UI | 4 |
| G | Cascade study | JEV and cascades (flagship) | 5 |
| H | CI gate | `evalhawk compare` | 6 |
| I | Expansion and launch | Clustering, RAG, integrations, PyPI | 7–9 |

## 5. Phases

### Phase 0: Foundation (2–3 days)

**Goal:** an empty but professional repo with CI.

1. ✅ Name chosen: `evalhawk` (package, import, GitHub org and repo), brand **EvalHawk**. Free on PyPI and GitHub on 2026-09-27.
2. ✅ GitHub organization [`evalhawk`](https://github.com/evalhawk), co-owned by both maintainers. Repo `evalhawk/evalhawk` is created at the end of this phase.
3. ✅ `src/` layout, `requires-python >= 3.11`, `pyproject.toml` (hatchling, four core dependencies, dependency groups `dev` and `docs`).
4. ✅ ruff (lint + format, including Markdown code blocks), pyright (strict on `core/` and `stats/`), pytest, hypothesis, import-linter.
5. ✅ pre-commit hooks.
6. ✅ GitHub Actions: lint, typecheck, layer rules, tests on Python 3.11/3.12/3.13 × Windows/Linux, strict docs build; docs deployment to GitHub Pages.
7. ✅ Docs: Zensical site, requirements, engineering standards, design patterns, limitations, ADRs 0001–0008, CONTRIBUTING, CHANGELOG, SECURITY.
8. MIT license (copyright line to be agreed by both maintainers).
9. First commit, create the public repo, push, branch protection, CODEOWNERS, confirm CI is green.
10. Publish `0.0.1` to PyPI early to secure the name, with both maintainers as owners.
11. Sign up for TypeSafe (JEV) and check access, pricing and free credits early.

**Done when:** a placeholder test passes in CI on both operating systems.

---

### Phase 1: Core models and interfaces (1 week)

**Goal:** the shapes of all data, plus the plug-in points.

1. `Trace`: input, output, model, optional `contexts` (for RAG later), `group_id` (for clustered error bars), metadata. The ID is a stable content hash. Field names follow the OpenTelemetry GenAI conventions.
2. `Criterion`: one binary question per failure mode, e.g. "Did the answer invent a fact?"
3. `Label` (human): trace, criterion, PASS/FAIL/UNKNOWN, annotator, split, timestamp.
4. `Verdict` (judge): trace, criterion, judge ID, outcome, optional probability, optional reasoning, cost, latency.
5. `Evaluation`: dataset + kind + criterion→judge mapping + estimator. Kinds: `single_turn`, `rag` (later `pairwise`, `agent`), each with **data-shape checks at load time** that name the offending row.
6. `Calibration` record per (judge, criterion): sensitivity, specificity, n, date, status. It becomes **stale** when the `judge_id` changes, when there are too few labels, or when Rogan-Gladen and PPI disagree.
7. Protocols: `Judge`, `TraceSource`, `Store`, `Target`.
8. `SQLiteStore`: WAL mode, `busy_timeout`, `PRAGMA user_version` migrations.
9. Split assignment: deterministic (based on a hash), **locked once assigned** by DB triggers. Every read of the test split is logged.
10. `JSONLSource` and `CSVSource` importers, **streaming** through iterators with batched inserts.
11. Golden tests that freeze content IDs and split assignment ([ADR-0006](decisions/0006-content-addressed-ids-and-splits.md)).

**Done when:** data round-trips through the store, and a test proves a split can't change after it's assigned.

---

### Phase 2: Statistics core (1–2 weeks). The heart of the project

**Goal:** trustworthy numbers, proven correct before any LLM is involved.

1. Agreement: TPR, TNR, precision, Cohen's kappa, each with a Wilson confidence interval.
2. Pass rate with a CI (Wilson and bootstrap).
3. **Bias-corrected pass rate** (Rogan-Gladen), with a CI that includes the uncertainty from the calibration set.
4. **PPI estimator** (prediction-powered inference), the modern alternative. Compare it against Rogan-Gladen.
5. **Paired comparison** of v1 vs v2: exact McNemar test plus paired bootstrap on the difference.
6. **Clustered standard errors** when traces share a `group_id`.
7. **Power analysis**: "you need N more examples to detect a difference of X."
8. Calibration metrics for judges that output probabilities: reliability bins, ECE, Brier score.
9. **Validation suite:**
   - Simulation: a synthetic judge with known TPR/TNR and known true pass rate. Over 2,000 runs, 95% CIs must contain the truth 93.5–96.5% of the time.
   - Hypothesis property tests (e.g. CIs always contain the point estimate, results don't depend on input order).
   - Cross-check against `ppi-python` within tolerance.

**Done when:** the coverage simulation passes and our results match `ppi-python`.
**Portfolio output:** a chart showing naive CIs missing the truth vs corrected CIs hitting 95%.

---

### Phase 3: Judges, runner and CLI (1–2 weeks)

**Goal:** real judges running on real data, fully free on a laptop.

1. `OpenAICompatibleJudge`: any `base_url`, structured PASS/FAIL/UNKNOWN output, probability taken from logprobs when the provider offers them. Config options `headers`, `verify` (CA bundle) and `timeout`.
2. `FunctionJudge`: wraps any Python callable.
3. Versioned judge prompt templates, one per criterion. The template hash becomes part of the judge ID.
4. Built-in targets: `CallableTarget`, `RecordedTarget`, `HttpTarget` (url, headers with `${ENV}` expansion, `{{input}}` body template, `answer_path`, `contexts_path`, timeout) and `OpenAICompatibleTarget`.
5. Async runner: concurrency limit, retries with backoff, timeouts, cost and latency tracking, `max_cost_usd` budget.
6. Cache keyed on `(trace_id, criterion_id, judge_id)`, so the same judgment is never paid for twice.
7. `repeats = k` (repeats are clustered by example in the statistics, plus pass^k for agents) and `--sample N` for large datasets.
8. `evalhawk.toml` config file; `wiring.py` builds every object from it.
9. CLI commands: `init`, `import`, `eval` (run + judge + report), `report`, `export` (CSV/JSONL), `judges status`, `judges compare` (Rich terminal output).
10. **First real validation:** convert the MT-Bench human judgments and LLMBar into traces and labels, run an Ollama judge, and report sensitivity and specificity ± CI.
11. **DeepEval adapter:** read DeepEval metric results (score ≥ threshold → PASS) so the trust layer works on them. Importing pre-recorded verdicts from files comes first (Stage D).

**Done when:** `evalhawk report` shows judge-vs-human agreement with CIs on public data.
**Milestone:** first showable version (about week 5).

---

### Phase 4: Labeling UI (1 week)

**Goal:** fast, unbiased human labeling.

1. `evalhawk ui` starts FastAPI on localhost.
2. Labeling screen: keys `P`, `F`, `U`, a notes field, `→` for next.
3. **Blind by default:** the judge's verdict is never shown while a human labels.
4. Queue strategies: random, uncertain-first, disagreement-first. Each item's selection probability is recorded, and the estimators use inverse-probability weights so results stay unbiased.
5. Criteria editor: add or rename criteria during labeling, with versioning. This handles "criteria drift", where people refine their idea of "good" as they label.
6. Report page: agreement table, corrected pass rate, reliability chart.
7. (Optional) Several annotators, with human-to-human agreement.

**Done when:** 100 labels take under 15 minutes, and the UI's numbers exactly match the CLI's.

---

### Phase 5: JEV and cascades (1–2 weeks). The headline phase

**Goal:** answer an open research question with your own measurements.

1. `JevJudge` via `typesafe-sdk`: always include an "unknown" option, and keep one fixed question format.
2. A local open alternative (a small Ollama model with logprobs).
3. Per-judge calibration report, with optional recalibration (isotonic or Platt) fitted on the dev split.
4. `CascadeJudge`: a cheap judge that escalates when unsure. The threshold is picked on the dev split. It is itself a `Judge`, so cascades compose.
5. **Error-correlation analysis:** compare P(strong judge wrong | cheap judge wrong) with what you'd expect if the two were independent.
6. Experiments on MT-Bench, LLMBar and JudgeBench: accuracy vs cost vs latency for JEV, an LLM judge, and the cascade.
7. Write the post: *"Does the JEV cascade actually work? I measured it."*

**Done when:** one command (`make experiments`) regenerates every figure.
**Milestone:** flagship portfolio piece (about week 9).

---

### Phase 6: Prompt comparison and CI gate (1 week)

1. `evalhawk compare runA runB` → **better / worse / inconclusive**, plus "you need N more examples".
2. Meaningful exit codes for CI.
3. A GitHub Action, plus an example workflow.

**Done when:** a demo repo blocks a pull request that introduces a *significant* regression, and lets through a change that's just noise.

---

### Phase 7: Failure discovery (1 week)

1. Embed human notes and judge reasoning (fastembed), then cluster them (HDBSCAN).
2. An LLM proposes a name for each cluster. A human confirms it, and it becomes a new `Criterion`. This closes the error-analysis loop.
3. A UI view of the clusters.

**Done when:** clusters on a real dataset match failure modes a person would recognize.

---

### Phase 8: RAG support (1–2 weeks)

1. RAG criteria: faithfulness, answer relevance, context relevance. They use `Trace.contexts`, which has existed since Phase 1.
2. Code-based retrieval metrics (recall@k, MRR, nDCG) when the correct document IDs are known.
3. Validate on RAGTruth (18k responses with human hallucination labels), and compare with Ragas on the same data.

**Done when:** a write-up that says "Ragas says X; the corrected estimate is Y ± Z."

---

### Phase 9: Launch (1 week)

1. Docs site polish: user guide, API reference and examples. The Zensical site itself exists from Phase 0.
2. `examples/`: quickstart, custom judge, RAG.
3. PyPI release through GitHub trusted publishing (no stored tokens).
4. Langfuse and OpenTelemetry import adapters.
5. Demo GIF, launch posts, resume bullets.

**Done when:** on a clean machine, `pip install` → quickstart runs in under 5 minutes.

### Later
- Agent step evaluation: tool-call and argument checks, step efficiency ([Agents](evals/agents.md))
- Multi-turn conversations ([Conversations](evals/conversations.md))
- Pairwise (head-to-head) judging with position swapping
- **Conditional criteria:** a criterion evaluated only if another passed (like DeepEval's DAG), with results reported for the right subset
- Ragas adapter · Postgres store

---

## 6. Milestones

| ~Week | What you can show |
|---|---|
| 1 | Professional repo with green CI |
| 4 | Stats core + chart showing the coverage simulation passes |
| 5 | Judge-vs-human report on public data (first demo) |
| 7 | Labeling UI |
| 9 | **JEV cascade study + blog post (flagship)** |
| 14–15 | Public launch on PyPI |

Rough total: **12–15 weeks part-time.**

## 7. Risks

| Risk | Mitigation |
|---|---|
| JEV access, price or API changes | Optional extra behind the `Judge` interface, with a local alternative |
| Scope creep | One default per interface; each phase ends shippable |
| Subtle stats bugs | Simulation coverage suite + cross-check against `ppi-python` |
| Free-tier rate limits | Caching + local Ollama |
| Someone ships something similar | Publish the Phase 5 study early; timing is the advantage |

## 8. Early decisions

| Decision | Outcome |
|---|---|
| Name | ✅ `evalhawk` / EvalHawk |
| Public from day 1, or private until Phase 3? | ✅ Public, in the `evalhawk` GitHub organization |
| Ownership | ✅ Shared by two maintainers (both org owners, both PyPI owners) |
| Build order | Stages A–I, proposed in [ADR-0007](decisions/0007-build-order.md) |
| Demo domain for the examples | Open (e.g. customer-support Q&A, or public datasets only) |
| JEV access | Open: sign up and confirm pricing and free credits |
| Hours per week | Open: sets the real timeline |
