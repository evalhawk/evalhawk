# ADR-0013: Live judging contracts

- **Status:** Proposed (awaiting approval by both maintainers)
- **Date:** 2026-11-01
- **Deciders:** Venkata Sai Karthik, Krishna Nandimandalam

## Context

Phase 4 makes EvalHawk call the user's application and LLM judges itself. That needs a
few decisions that touch core contracts, dependencies and the storage schema.

## Decision

1. **Judges receive the example.** The `Judge` port becomes
   `judge(example, trace, criterion)` (previously `judge(trace, criterion)`). A judge's
   prompt needs the question, reference and contexts, and a trace stores only the answer.
   `MultiCriterionJudge.judge_many` changes the same way.
2. **A judgment cache keyed by everything the judge sees.** `judgment_key()` hashes input,
   reference, output, contexts, criterion and judge ID, and **excludes run, version and
   repeat**. Verdicts stay keyed by `(trace, criterion, judge)`; the new `judgments` table
   (schema migration 3) lets identical content be reused across versions and repeats.
   The runner also deduplicates identical judgments that are in flight at the same time.
3. **No new runtime dependencies.** Judges and targets talk HTTP through
   `evalhawk.transport.http` (standard library `urllib`), not the `openai` package. Any
   OpenAI-compatible endpoint works (Ollama, OpenAI, Groq, OpenRouter, vLLM).
4. **Secrets never persist.** `${VAR}` placeholders in config are expanded only when
   adapters are built; the run's saved configuration keeps the placeholder. API keys come
   from `api_key_env`. A test asserts a secret used in a header is absent from the database.
5. **`judge_id` hashes behaviour, not transport.** For LLM judges: adapter, model, base
   URL, mode, sampling parameters, prompt template and guidance texts. Not: API keys,
   headers, TLS settings or timeouts. Editing built-in guidance therefore creates a new
   judge that must be re-calibrated. Function judges hash a user-supplied `version`.
6. **Runs resume by configuration.** `evalhawk eval` reuses the stored run whose version
   and saved configuration match; `--fresh` starts a new one. A changed judge, prompt,
   criterion or split always means a new run.
7. **A run may hold several criteria and judges.** The run snapshot lists
   `{name, criterion_id, judge, judge_id}` entries; `report`, `compare` and `judges` select
   one with `--criterion` / `--judge`. Recorded-import runs keep their old shape.

## Consequences

**Positive**

- Live evaluation with zero extra dependencies; reruns and unchanged answers cost nothing.
- Configuration mistakes fail before any paid call.

**Negative**

- The `Judge` signature change breaks third-party judges written against the old shape
  (none exist yet; pre-1.0).
- We maintain a small HTTP client and a JSONPath subset ourselves.
- The judgment cache assumes a deterministic judge. Sampling noise in a judge is not
  re-measured for identical content (judge noise is handled by calibration instead).

## Alternatives considered

| Option | Why not |
|---|---|
| `openai` SDK as an `[llm]` extra | Heavier install for one endpoint we can call in ~60 lines |
| Cache keyed by `(trace, criterion, judge)` only | Pays again for identical answers in new versions and repeats |
| Expand `${VAR}` at config load | The expanded secret would be saved in the run snapshot |
