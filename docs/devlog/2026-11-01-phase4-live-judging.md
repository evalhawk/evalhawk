# Phase 4 · Live judging

- **Author:** Venkata Sai Karthik (with Claude Code)
- **Date:** 2026-11-01
- **Roadmap:** Phase 4 / Stage E · **PR:** *(added when opened)*

## What I built

EvalHawk can now run your app and its judges itself:

- **Judges** (`judges/`): a prompt judge with strict verdict parsing, an
  OpenAI-compatible judge (Ollama, OpenAI, Groq, ...) on the standard library, function
  judges, **13 code checks** and **11 built-in criteria** with guidance and sources.
- **Targets** (`targets/`): a Python function, an HTTP API (body templates + JSONPath), an
  OpenAI-compatible model, or recorded outputs.
- **Runner** (`runner/`): resume, a judgment-key cache, in-flight deduplication, retries
  with backoff and jitter, timeouts and a budget.
- **Config and CLI**: `evalhawk.toml`, `evalhawk init`, `eval`, `judges status`,
  `judges compare`, `export`.

## The idea, simply

Think of the runner as a careful assistant marking a stack of exam papers with help:

- It **never re-marks** a paper it already marked (resume), and if two papers contain the
  exact same answer, it marks it once and copies the mark (judgment-key cache).
- It keeps only a few markers busy at once (concurrency), asks again politely when one is
  temporarily unavailable (retries with backoff), gives up on one who takes too long
  (timeout) and stops hiring once the budget is spent.
- Anything that goes wrong is written down, never silently skipped.

## How I know it's right

- 64 new tests, 400 in total: parsing, every code check, prompt contents, `judge_id`
  stability, real HTTP round trips against a local fake server, and end-to-end CLI runs.
- Runner promises are tested one by one: resume makes zero calls, identical answers in a
  new version make zero judge calls, repeats share one judgment, retryable vs
  non-retryable errors, timeouts, the concurrency limit and the budget.
- A **secret** placed in a judge header is sent on the request but never appears in the
  database.

## What surprised me / gotchas

- **The budget test caught a real bug.** Checking the budget *before* waiting for a free
  call slot let every queued call pass while spend was still zero, so all 10 were paid
  for. Checking after acquiring the slot fixed it: 3 calls for a 2.5 budget at 1.0 each.
- **Concurrent repeats defeat a naive cache.** Identical answers judged at the same moment
  all miss the cache together, so in-flight judgments are shared.
- **The docs had a real bug:** an HTTP body written as a TOML string would be sent as a
  JSON string. The target now parses string bodies as JSON templates, and the docs use
  tables.
- **My test assumption was wrong, not the code:** the quickstart bot misses 4 of 8
  questions ("ship" isn't "shipping"), so the PII check fails 4 times, not 2.

## How AI helped (and where it was wrong)

Claude Code designed and wrote the phase test-first. Its first test file had leftover junk
code and a weak secrets test; both were rewritten. Its scripted edits twice broke files
(a shell heredoc and literal newlines in strings), caught immediately by the tools.

## Learn more

- [ADR-0013: Live judging contracts](../decisions/0013-live-judging-contracts.md)
- Exponential backoff and jitter: AWS Architecture Blog, "Exponential Backoff And Jitter"
- [G-Eval](https://arxiv.org/abs/2303.16634), [RAGAS](https://arxiv.org/abs/2309.15217),
  [FActScore](https://arxiv.org/abs/2305.14251) (sources of the built-in criteria)
