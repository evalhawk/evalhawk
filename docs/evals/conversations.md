# Conversations (multi-turn)

!!! warning "Later"
    Multi-turn evaluation is on the roadmap under **Later**. This page records the intended
    design so the data model stays compatible. Until then, test single turns with
    [Chatbots and Q&A](chatbots.md), passing earlier messages as part of the input.

## What it covers

Evaluating a **whole conversation**, not one reply: support chats, tutoring sessions,
sales assistants.

## What can go wrong

| Failure | Example |
|---|---|
| Forgets earlier information | Asks for the order number the user already gave |
| Drifts from its role | A support bot starts giving legal advice |
| Never resolves the issue | A polite but endless loop |
| One bad turn | Nine good replies and one rude one |

## Planned evals

| Eval | Question it asks | Level |
|---|---|---|
| `remembers_context` | Does the assistant use information given earlier? | Whole conversation |
| `stays_in_role` | Does it stay within its role throughout? | Whole conversation |
| `resolved` | Was the user's goal achieved by the end? | Whole conversation |
| Per-turn criteria | Any single-turn criterion, applied to every assistant turn | Each turn |

Source for the approach: multi-turn judging in [MT-Bench](https://arxiv.org/abs/2306.05685)
(Zheng et al., 2023).

## The statistical point to get right

Turns in one conversation are **related**, like repeated agent runs. Per-turn results must
be clustered by conversation, or 50 conversations × 10 turns will look like 500
independent tests and the error ranges will be far too narrow. The existing `group_id`
mechanism already supports this.

## Planned data format

```json
{"conversation_id": "c-17", "turns": [
  {"role": "user", "content": "My order hasn't arrived"},
  {"role": "assistant", "content": "Sorry to hear that. What's your order number?"},
  {"role": "user", "content": "A-1042"}
]}
```

## Compared with DeepEval

DeepEval already offers Knowledge Retention, Role Adherence, Conversation Completeness and
Conversation Relevancy. When EvalHawk adds conversations, its difference will be the same
as everywhere else: calibrated verdicts and clustered error ranges.
