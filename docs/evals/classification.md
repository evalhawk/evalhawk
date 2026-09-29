# Classification and extraction

!!! info "Planned: Phase 4"

## What it covers

Systems where each input has a **known correct answer**:

- **Classification:** spam or not, intent routing ("billing", "technical", "sales"),
  sentiment, priority.
- **Extraction:** pull fields out of text, such as the order number, date or amount.

## What can go wrong

| Failure | Example |
|---|---|
| Wrong label | A billing question routed to "technical" |
| Wrong or missing field | Extracts the wrong date, or none at all |
| Wrong format | "Billing." instead of "billing" |

## The evals

These need **no AI judge**: the correct answer is known, so a code check is exact.

| Eval | Question it asks | How it works | Needs |
|---|---|---|---|
| `exact_match` | Does the output equal the reference? | String comparison, with optional normalisation (case, whitespace, punctuation) | `output`, `reference` |
| `one_of` | Is the output one of the allowed labels? | Membership check | `output` |
| `field_match` | Does each extracted field match? (one criterion per field) | Parse the output, compare the field | `output` (JSON), `reference` (JSON) |
| `regex` | Does the output match a pattern (e.g. an order number)? | Regular expression | `output` |

These are standard exact-match checks; no specific paper is needed.

## Why the trust layer still matters here

Code checks don't need a human to verify them, because they're exactly right. But
EvalHawk still gives you:

- **An error range** on the accuracy: "94% [92% – 96%] on 800 examples".
- **Per-class results**, so a rare class that's always wrong isn't hidden by the average.
- **A version comparison**: is the new model *really* better at routing, or is it noise?

## What you provide

```json
{"input": "I was charged twice this month", "reference": "billing"}
{"input": "The app crashes when I log in", "reference": "technical"}
```

For extraction, `reference` holds the expected fields:

```json
{"input": "Order #A-1042 placed on 3 March for £59.00", "reference": {"order_id": "A-1042", "amount": "59.00"}}
```

## How it's tested

1. Each input goes to your system.
2. Code checks compare each output with the reference: instant and free.
3. The report shows accuracy with error ranges, overall and per class or field.
4. `evalhawk compare` tells you whether a new version is better, worse, or can't be told apart yet.

## Example config

```toml
[target]
type     = "callable"
callable = "my_app.router:classify"

[[criteria]]
id    = "correct_intent"
check = { type = "exact_match", normalise = ["case", "whitespace"] }

[[criteria]]
id    = "valid_label"
check = { type = "one_of", values = ["billing", "technical", "sales"] }

[evaluations.router]
dataset  = "data/intents.jsonl"
kind     = "single_turn"
criteria = { correct_intent = "code", valid_label = "code" }
```

## What you get

Illustrative output:

```text
correct_intent   94%  [92% – 96%]   n = 800
  billing        97%  [95% – 99%]   n = 410
  technical      93%  [89% – 96%]   n = 300
  sales          81%  [72% – 88%]   n =  90   ← weakest class
valid_label      100% [99% – 100%]
```

## Compared with DeepEval

DeepEval focuses on AI-judged metrics; exact-match checks are written as custom code.
EvalHawk ships them as built-ins, with error ranges, per-class breakdowns and statistical
version comparison.
