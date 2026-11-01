# EvalHawk

**Trustworthy LLM evaluation.** Bring your own model, judge and data. EvalHawk makes the numbers trustworthy.

> **Status: alpha.** Everything below runs today. APIs and config may still change before 0.1.
> Not on PyPI yet: install from GitHub.

## The problem

Teams grade LLM outputs with LLM judges and then trust the scores. But judges make mistakes, test sets are small, and "v2 scored 83% vs v1's 78%" is often just noise.

EvalHawk measures how wrong your judge is (against blind human labels), removes that bias from the pass rate, and puts an honest error bar on every number.

## Try it in one minute (no API key, no GPU)

```bash
uv tool install "evalhawk[ui] @ git+https://github.com/evalhawk/evalhawk"
evalhawk init support-bot && cd support-bot   # a tiny bot, a dataset, a config
evalhawk eval -t v1
```

```text
               Judged pass rates (uncorrected, all piles)
| Criterion        | Judge | Pass rate | 95% interval    | n | UNKNOWN |
|------------------+-------+-----------+-----------------+---+---------|
| not_empty        | code  | 100.0%    | [67.6%, 100.0%] | 8 | 0%      |
| concise          | code  | 100.0%    | [67.6%, 100.0%] | 8 | 0%      |
| no_personal_data | code  | 50.0%     | [21.5%, 78.5%]  | 8 | 0%      |
```

Two things to notice. The PII check caught a real bug: the fallback reply leaks `support@example.com`. And with 8 examples, "100%" really means "somewhere above 68%". EvalHawk never shows a number without its interval.

Point `[target]` at your own function, HTTP API or OpenAI-compatible model, add an LLM judge (Ollama works free and offline), and you are evaluating your real app.

## Why the correction matters

The offline demo (`evalhawk demo init demo`, see [getting started](docs/getting-started.md#offline-support-bot-demo)) has a judge that passes too much. After about 370 blind human labels:

```text
                               Judge report card (dev)
| Sensitivity | 0.935    | [0.899, 0.959] | 95%        | 262 | wilson                 |
| Specificity | 0.623    | [0.528, 0.709] | 95%        | 106 | wilson                 |
                         Representative-case pass rates (test)
| Naive judge  | 0.792    | [0.750, 0.828] | 95%        | 413 | wilson                 |
| Rogan-Gladen | 0.743    | [0.646, 0.830] | 95%        | 413 | rogan_gladen+bootstrap |
| PPI          | 0.729    | [0.674, 0.785] | 95%        | 413 | ppi                    |
```

The judge misses 38% of real failures, so its 79% is inflated. The corrected estimate is about 73%, with an interval that honestly includes the extra uncertainty. Comparing versions works the same way:

```text
| Judged (uncorrected)    | 0.027    | [-0.027, 0.078] | paired_cluster_bootstrap      |
| Corrected for the judge | 0.053    | [-0.051, 0.159] | paired_rogan_gladen+bootstrap |
Decision: INCONCLUSIVE
```

That is the right answer: the correction removes bias but cannot create information, so the tool says "inconclusive" rather than declaring a winner.

## What it does

| | |
|---|---|
| **Calibrate judges** | Blind labelling in a local web app (`evalhawk ui`); sensitivity, specificity, kappa per (judge, criterion) |
| **Corrected pass rates** | Rogan-Gladen and prediction-powered inference (PPI), always with intervals |
| **Paired comparisons** | v2 vs v1 on the same examples: better / worse / inconclusive, optionally bias-corrected |
| **CI gate** | `evalhawk gate` and a [GitHub Action](action.yml) that fail a PR on a significant regression |
| **Judges** | Any OpenAI-compatible model, 13 free code checks (regex, JSON schema, PII, ...), your own Python function, plugins, cheap-then-strong cascades |
| **Criteria** | 11 built-ins (correctness, faithfulness, context relevance, safety, ...) or your own yes/no question |
| **RAG** | Faithfulness criteria plus retrieval metrics: hit@k, recall@k, precision@k, MRR, nDCG@k |
| **Failure discovery** | `evalhawk discover` clusters judge reasoning and human notes into candidate new criteria |
| **Honest by construction** | Hash-locked dev/test splits (DB-enforced), logged test reads, content-addressed caching and resume, secrets never stored |

Lean dependencies: NumPy, Pydantic, Typer. No torch, no SciPy at runtime; the web UI is an optional extra.

## Examples

- [`examples/rag-support`](examples/rag-support): a RAG bot with a custom Python judge and retrieval metrics, fully offline
- [`examples/ci`](examples/ci): gate pull requests on evaluation regressions

## Documentation

- [Getting started](docs/getting-started.md): every command, step by step
- [Requirements](docs/requirements.md) · [Roadmap](docs/roadmap.md) · [Architecture](docs/architecture.md)
- [Design patterns](docs/design/patterns.md) · [Decision records](docs/decisions/index.md)
- [Limitations](docs/limitations.md): assumptions and known limits (read this before trusting any number)

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups          # create .venv and install everything
uv run pre-commit install     # run the checks on every commit
uv run pytest                 # tests (add -m "not slow" for a fast run)
uv run ruff check . && uv run pyright && uv run lint-imports
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow.

## Maintainers

EvalHawk is built and co-owned by **Venkata Sai Karthik** ([@EVSGoud](https://github.com/EVSGoud)) and **Krishna Nandimandalam** ([@kclectic0501](https://github.com/kclectic0501)).
How we work together: [maintainer agreement](docs/development/collaboration.md) · [work plan](docs/development/workplan.md) · [dev log](docs/devlog/index.md).

## License

[MIT](LICENSE)
