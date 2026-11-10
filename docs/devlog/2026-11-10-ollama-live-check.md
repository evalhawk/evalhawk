# Live check · EvalHawk with a real local judge (Ollama)

- **Author:** Venkata Sai Karthik
- **Date:** 2026-11-10
- **Card:** live judging follow-up · **PR:** #36

## What I built

The first end-to-end run of EvalHawk against a **real** LLM judge: Ollama 0.40.15 with
`qwen3.5:4b` on a laptop. Until now every LLM-judge test used a fake server. The run found
three bugs, which are fixed here:

| Bug | Symptom | Fix |
|---|---|---|
| Thinking models spend `max_tokens` on hidden reasoning | 15 of 16 verdicts were UNKNOWN: `Unparseable judge reply: ''` | `reasoning_effort` option on judges and OpenAI-compatible targets; a clear error when a reply is empty because it hit the token limit |
| The reference answer was shown for every criterion | `polite` failed polite answers "because the reference says otherwise" | Prompt v2: the reference is shown only to criteria that need it |
| Built-in guidance was looked up by name only | A renamed built-in (`name = "accurate"`, `template = "correctness"`) silently lost its guidance | Built-ins are also recognised by their question |

Smaller fixes: replies cut off before their `VERDICT:` line now say so; `judges cascade`
prints a valid TOML snippet; `--help` no longer crashes on Windows consoles that use cp1252
(a `→` in a help string); failure-discovery key words skip judge filler ("reference",
"assistant's", "whereas").

`experiments/scripts/ollama_live_check.py` repeats the whole check on anyone's machine.

## The idea, simply

A "thinking" model is like a student who must show their rough work on the same page as the
answer. Give them half a page and they may fill it with rough work and never write the answer.
`reasoning_effort = "none"` tells them to skip the rough work.

The reference fix is about anchoring: show a judge the "right answer" while asking whether a
reply is *polite*, and a small model starts grading correctness instead.

## How I know it's right

The live check builds 84 support questions over 14 policy facts, with two recorded bot
versions whose mistakes we wrote ourselves (wrong numbers, invented features, "I'm not sure"),
so the truth is known for every answer. Every verdict comes from the real model.

| What | Result |
|---|---|
| Judging, 2 versions × 84 answers × 2 judges | 367 s on a laptop, 0 UNKNOWN, 0 failures |
| Judge vs answer key, dev / test | 100% (64/64) / 93.1% (67/72) |
| v1 pass rate: corrected (PPI) vs truth | 58.3% [42.2%, 74.4%] vs 58.3% |
| v2 pass rate: corrected (PPI) vs truth | 80.6% [67.6%, 93.5%] vs 81.0% |
| Cheap one-word judge on v1: judged → corrected (PPI) vs truth | 63.9% → 60.8% [44.0%, 77.6%] vs 58.3%: the correction moves a biased judge toward the truth |
| v2 − v1, corrected | +22.2 points [+8.3, +36.1]: BETTER; the gate passes |
| Cascade: one-word judge with P(PASS), then the reasoning judge | cheap alone 96.9% on dev; escalating 1 in 32 reaches 100% |
| RAG `faithfulness` on the RAG example | 10/10 sensible: the invented loyalty programme FAILs |
| Failure discovery with `--namer` | 3 sensible clusters (refusals, contradictions, invented loyalty) |

Unit tests pin each fix: `reasoning_effort` is sent and changes the judge ID only when set;
an empty, truncated reply raises a non-retryable error naming the cause; the reference
appears only for criteria that need it; a renamed built-in keeps its guidance; CLI sources
are ASCII.

## What surprised me / gotchas

- **The judge looked perfect on dev (32/32) but made 5 mistakes on test (67/72).** With 32
  calibration labels, "perfect" only means sensitivity ≥ 0.80 and specificity ≥ 0.82 (the
  Wilson lower bounds), and the report shows exactly that. More labels would narrow it.
- Four of the five "mistakes" are debatable: "Can I contact support on Saturday?" answered
  with "Open 9am–5pm, Monday to Friday" was failed for not saying "no". The genuine miss: an
  answer listing two invented payment methods passed.
- The 4B model's proposed criterion names were mixed: one good, one with the wrong polarity,
  one nonsense ("Does the restaurant offer…"). A human must review every proposal.
- Ollama's documentation lists logprobs as unsupported on `/v1/chat/completions`, yet
  Ollama 0.40.15 returned them for `qwen3.5:4b`, and the cascade relies on them. If a future
  version drops them, the cheap judge gives no probability and `judges cascade` says so.
- Prompt v2 changes every LLM judge's ID, so earlier verdicts and calibrations are not reused.
  That is the point of content-addressed judges: a different prompt is a different judge.

## How AI helped (and where it was wrong)

Claude Code ran the live checks, diagnosed each bug from raw Ollama replies, and wrote the
fixes and tests. It earlier assumed Ollama wasn't installed and had tested only against a fake
server; the real run is what exposed the thinking-model and reference problems.

## Learn more

- Ollama's OpenAI compatibility, including `reasoning_effort`:
  <https://docs.ollama.com/api/openai-compatibility>
- Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena* (2023): reference-guided
  grading for correctness.
