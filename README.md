# EvalHawk

**Trustworthy LLM evaluation.** Bring your own model, judge and data. EvalHawk makes the numbers trustworthy.

> 🚧 **Status: pre-alpha, Phase 0 (foundation).** Nothing is usable yet. Follow along in the [roadmap](docs/roadmap.md).

## The problem

Teams grade LLM outputs with LLM judges and then trust the resulting scores. But judges make mistakes, test sets are small, and "v2 scored 83% vs v1's 78%" is often just noise.

## What EvalHawk will do

1. **Calibrate your judge against humans.** A fast, blind labeling UI measures how often the judge agrees with people (sensitivity, specificity, calibration).
2. **Correct for the judge's bias.** Pass rates are bias-corrected (Rogan-Gladen, prediction-powered inference) and always come with error bars.
3. **Compare versions honestly.** Paired tests tell you whether v2 is *really* better, worse, or "not enough data yet".
4. **Work with anything.** Any OpenAI-compatible model or endpoint, cheap judges like JEV, your own HTTP API, or pre-recorded outputs.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups          # create .venv and install everything
uv run pre-commit install     # run the checks on every commit
uv run pytest                 # tests
uv run ruff check .           # lint
uv run pyright                # type-check
uv run lint-imports           # architecture layer rules
uv run evalhawk --version     # the CLI
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow.

## Documentation

- [Requirements](docs/requirements.md): what EvalHawk does, and how well
- [Roadmap](docs/roadmap.md): phases, build order and milestones
- [Architecture](docs/architecture.md): design, data model, statistics, concepts
- [Design patterns](docs/design/patterns.md): the low-level design and the intuitions behind it
- [Engineering standards](docs/development/standards.md): the rules every change follows
- [Decision records](docs/decisions/index.md): why things are the way they are
- [Limitations](docs/limitations.md): assumptions and known limits

## Maintainers

EvalHawk is built and co-owned by **Venkata Sai Karthik** ([@EVSGoud](https://github.com/EVSGoud)) and **Krishna Nandimandalam** ([@kclectic0501](https://github.com/kclectic0501)).
How we work together: [maintainer agreement](docs/development/collaboration.md) · [work plan](docs/development/workplan.md) · [dev log](docs/devlog/index.md).

## License

[MIT](LICENSE)
