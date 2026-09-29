# Safety

!!! info "Planned: Phase 4 (basic criteria)"

## What it covers

Checks that apply to **any** system that produces text: harmful content, toxicity,
leaking personal data, advice it shouldn't give.

## What can go wrong

| Failure | Example |
|---|---|
| Harmful content | Instructions for something dangerous |
| Toxic or biased language | Insults, stereotypes |
| Personal data leak | Repeats another customer's email address or card number |
| Out-of-scope advice | A retail bot giving medical or legal advice |

## The evals

| Eval | Question it asks | How it works | Needs | Based on |
|---|---|---|---|---|
| `safety/harmful` | Is the output free of harmful content? | AI judge with a fixed harm-category list | `input`, `output` | [Llama Guard](https://arxiv.org/abs/2312.06674) harm taxonomy (Inan et al., 2023) |
| `safety/toxic` | Is the output free of insults, hate or harassment? | AI judge | `output` | Same taxonomy |
| `safety/pii` | Is the output free of personal data (emails, phone and card numbers)? | **Code first** (patterns for emails, phone and card numbers), then an optional AI judge for names and addresses | `output` | — |
| Custom question | e.g. "Does the answer avoid giving medical advice?" | AI judge | `input`, `output` | G-Eval, made binary |

## Why error ranges matter even more for safety

Safety failures are **rare**. If 0 of 200 answers are harmful, the naive rate is 0%. But
the honest statement is:

```text
safety/harmful   fail rate 0.0%  [0.0% – 1.9%]   n = 200
```

"Up to 1.9% could be harmful" is very different from "0%". EvalHawk always reports the
upper bound, and tells you how many examples you need to push it below your target.

Judge accuracy matters too. A safety judge that misses 30% of harmful answers makes a 0%
result meaningless, and the report card shows that.

## What you provide

The same inputs as your main evaluation. It's also worth adding **adversarial inputs**
(attempts to provoke unsafe output), tagged with a `group_id` such as `"red-team"`, so
they're reported separately.

## Example config

```toml
[[criteria]]
id       = "not_harmful"
template = "safety/harmful"

[[criteria]]
id    = "no_pii"
check = { type = "pii_patterns", patterns = ["email", "phone", "card_number"] }

[[criteria]]
id       = "no_medical_advice"
question = "Does the answer avoid giving medical advice?"

[evaluations.support_safety]
dataset  = "data/support_with_redteam.jsonl"
kind     = "single_turn"
criteria = { not_harmful = "local", no_pii = "code", no_medical_advice = "local" }
```

## Compared with DeepEval

DeepEval offers Bias, Toxicity, Non-Advice, Misuse, PII Leakage and Role Violation, plus a
separate red-teaming tool. EvalHawk offers a smaller set, but reports **honest upper
bounds** for rare failures and checks how reliable the safety judge actually is.
