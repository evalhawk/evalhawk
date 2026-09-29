# Structured output

!!! info "Planned: Phase 4"

## What it covers

Systems that must return **machine-readable** output: JSON for an API, arguments for a
function call, a filled-in form, a database query.

## What can go wrong

| Failure | Example |
|---|---|
| Not valid JSON | A missing bracket, or text before the `{` |
| Wrong shape | A required field missing, or a string where a number belongs |
| Valid shape, wrong content | `"currency": "USD"` for a price in pounds |

## The evals

| Eval | Question it asks | How it works | Needs |
|---|---|---|---|
| `valid_json` | Does the output parse as JSON? | Code | `output` |
| `json_schema` | Does it match your JSON Schema (required fields, types, allowed values)? | Code, JSON Schema validation | `output`, a schema file |
| `field_match` | Is a specific field correct? | Code comparison with the reference | `output`, `reference` |
| Custom question | Is the content sensible? e.g. "Does the summary field describe the ticket accurately?" | AI judge | `input`, `output` |

Shape checks are exact, so they need no human labels. Content checks are AI-judged and go
through the [trust layer](trust-layer.md).

Validation follows the [JSON Schema](https://json-schema.org/) standard. Draft support and
the validator library will be chosen, and recorded in an ADR, when this is built.

## What you provide

```json
{"input": "Invoice from ACME, total £1,200, due 30 June", "reference": {"vendor": "ACME", "total": 1200, "currency": "GBP"}}
```

Plus a schema file, e.g. `schemas/invoice.json`.

## How it's tested

1. Your system produces output for each input.
2. `valid_json`, then `json_schema`, run instantly. An output that fails to parse is
   marked FAIL for the other checks, not UNKNOWN, so failures aren't hidden.
3. Field and content checks run on the outputs that parsed.
4. The report shows how often the output is valid, how often it has the right shape, and
   how often it's correct, as separate numbers.

## Example config

```toml
[[criteria]]
id    = "valid_json"
check = { type = "valid_json" }

[[criteria]]
id    = "matches_schema"
check = { type = "json_schema", schema = "schemas/invoice.json" }

[[criteria]]
id    = "total_correct"
check = { type = "field_match", field = "total" }

[evaluations.invoices]
dataset  = "data/invoices.jsonl"
kind     = "single_turn"
criteria = { valid_json = "code", matches_schema = "code", total_correct = "code" }
```

## What you get

Illustrative output:

```text
valid_json       99.2% [98.3% – 99.6%]
matches_schema   96.0% [94.4% – 97.2%]
total_correct    91.5% [89.4% – 93.3%]
```

## Compared with DeepEval

DeepEval has a **JSON Correctness** metric that validates output against a schema.
EvalHawk splits validity, shape and content into separate criteria, and adds error ranges
and version comparison.
