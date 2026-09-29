# Summarization

!!! info "Planned: Phase 4 (as criteria), Phase 8 (coverage check)"

## What it covers

Systems that turn a long text into a shorter one: ticket summaries, meeting notes,
document abstracts, email digests.

## What can go wrong

| Failure | Example |
|---|---|
| Adds facts that aren't in the source | "The customer asked for a refund" when they didn't |
| Leaves out something important | Skips the deadline mentioned in the meeting |
| Too long, or the wrong format | Five paragraphs when three bullets were asked for |

## The evals

| Eval | Question it asks | How it works | Needs | Based on |
|---|---|---|---|---|
| `summary/faithfulness` | Is every statement in the summary supported by the source? | Split the summary into claims; check each against the source; PASS if all are supported | `input` (the source), `output` | [FActScore](https://arxiv.org/abs/2305.14251) (Min et al., 2023) |
| `summary/coverage` | Does the summary include the key points? | 1. The judge writes yes/no questions from the **source**. 2. It answers them from the **summary**. PASS if enough are answerable (your threshold) | `input`, `output` | [QAGS](https://arxiv.org/abs/2004.04228) (Wang et al., 2020) |
| `max_words`, `bullet_count`, `regex` (code) | Length and format rules | Code, no AI | `output` | — |

Faithfulness and coverage pull in opposite directions: a one-line summary is faithful but
misses a lot. Always use **both**.

## What you provide

```json
{"input": "<full ticket or document text>", "group_id": "customer-4812"}
```

Use `group_id` when several source texts belong together (for example, tickets from the
same customer), so the error ranges stay honest.

## How it's tested

1. Each source text is sent to your summarizer.
2. Code checks run on each summary; `faithfulness` and `coverage` are AI-judged and cached.
3. You label about 100 summaries per AI criterion. Reading the source is needed, so
   labeling summaries takes longer than chatbot answers; EvalHawk shows the source and
   the summary side by side.
4. The report shows corrected pass rates for faithfulness and coverage separately.

## Example config

```toml
[target]
type     = "callable"
callable = "my_app.summaries:summarize"

[[criteria]]
id       = "faithful"
template = "summary/faithfulness"

[[criteria]]
id       = "covers_key_points"
template = "summary/coverage"

[[criteria]]
id    = "short"
check = { type = "max_words", value = 120 }

[evaluations.ticket_summaries]
dataset  = "data/tickets.jsonl"
kind     = "single_turn"
criteria = { faithful = "local", covers_key_points = "local", short = "code" }
```

## What you get

Illustrative output:

```text
faithful            89%  [85% – 92%]   judge ✅ ok (n=100)
covers_key_points   71%  [65% – 77%]   judge ✅ ok (n=100)
short               99%  [98% – 100%]  code
```

## Compared with DeepEval

| | DeepEval | EvalHawk |
|---|---|---|
| Method | Summarization metric (question-answer based), one combined 0–1 score | Faithfulness and coverage as **separate** yes/no criteria |
| Why it matters | A combined score hides *which* problem you have | You see whether the summary invents facts or misses them |
