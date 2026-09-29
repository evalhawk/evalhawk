# EvalHawk

**Trustworthy LLM evaluation.** Bring your own model, judge and data. EvalHawk makes the
numbers trustworthy.

!!! warning "Pre-alpha"
    EvalHawk is in Phase 0 (foundation). Nothing is usable yet. Follow along in the
    [roadmap](roadmap.md).

## The problem

Teams grade LLM outputs with LLM judges, then trust the scores. But judges make mistakes,
test sets are small, and related questions aren't independent. "v2 scored 85% vs v1's 82%"
is often just noise.

## What EvalHawk does

1. **Calibrates your judge against humans.** A fast, blind labeling UI measures how often
   the judge agrees with people.
2. **Corrects for the judge's bias.** Pass rates are bias-corrected (Rogan-Gladen,
   prediction-powered inference) and always come with confidence intervals.
3. **Compares versions honestly.** Paired tests say whether v2 is really better, worse, or
   "not enough data yet: you need about N more examples".
4. **Works with anything.** Any OpenAI-compatible model, cheap judges like JEV, your own
   HTTP API, or pre-recorded outputs.

A result looks like this:

```text
no_fabrication   0.781 [0.742, 0.816]   (ppi, n=412, unknown=1.2%)
```

## Where to go next

| If you want to... | Read |
|---|---|
| See how each kind of AI system will be tested | [Evaluating AI systems](evals/index.md) |
| Compare EvalHawk with DeepEval | [Features and comparison](features.md) |
| Set up a development environment | [Getting started](getting-started.md) |
| Know what EvalHawk will and won't do | [Requirements](requirements.md) and [Limitations](limitations.md) |
| Understand the design | [Architecture](architecture.md) and [Design patterns](design/patterns.md) |
| Contribute code | [Engineering standards](development/standards.md) |
| Know why things are the way they are | [Decision records](decisions/index.md) |
