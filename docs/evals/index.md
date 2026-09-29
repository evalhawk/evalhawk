# Evaluating AI systems

!!! info "Planned"
    This section describes how EvalHawk **will** work. Nothing here is implemented yet;
    the phase for each feature is shown on its page. Config and output formats are drafts
    and may change.

This section is organised **by the kind of AI system you want to test**. Each page follows
the same structure:

1. **What it covers**: which systems the page is for
2. **What can go wrong**: the failure modes worth testing
3. **The evals**: which checks to use, how each one works, and where the method comes from
4. **What you provide**: the data format
5. **How it's tested**: step by step
6. **Example config** and **what you get back**
7. **Compared with DeepEval**

## Pick your system

| Your system | Examples | Page | Available from |
|---|---|---|---|
| Chatbot / Q&A | Support bot, internal assistant | [Chatbots and Q&A](chatbots.md) | Phase 4 |
| RAG | "Ask our docs", search-then-answer bots | [RAG systems](rag.md) | Phase 4 (answers), Phase 8 (retrieval) |
| Summarizer | Ticket, meeting or document summaries | [Summarization](summarization.md) | Phase 4 |
| Classifier / extractor | Spam detection, intent routing, field extraction | [Classification and extraction](classification.md) | Phase 4 |
| Structured output | JSON, function arguments, forms | [Structured output](structured-output.md) | Phase 4 |
| Agent | Multi-step, tool-using systems | [Agents](agents.md) | Phase 4 (outcomes), later (steps) |
| Multi-turn chat | Whole conversations | [Conversations](conversations.md) | Later |
| Any system | Harmful content, personal data leaks | [Safety](safety.md) | Phase 4 |

## The one idea behind every page

Every eval in EvalHawk is a **criterion**: one yes/no question about one way the system
can fail ([ADR-0003](../decisions/0003-binary-criteria-only.md)). Each answer gets
**PASS**, **FAIL** or **UNKNOWN**.

There are four ways to define a criterion:

| Kind | What it is | Needs an AI judge? | Example |
|---|---|---|---|
| **Code check** | A deterministic rule | No | "Is the output valid JSON?" |
| **Built-in template** | A ready-made, documented judge prompt | Yes | `faithfulness`, `answer_relevance` |
| **Custom question** | Any yes/no question in plain English | Yes | "Does the answer apologise when the customer is upset?" |
| **External metric** | A DeepEval metric or your own function | Depends | DeepEval `FaithfulnessMetric` (score ≥ threshold → PASS) |

## The lifecycle, the same for every system

```
1. Define     criteria (what "good" means)
2. Run        your system on the test inputs          evalhawk eval
3. Judge      every answer against every criterion    (cached: never paid twice)
4. Label      ~100 answers yourself, blind            evalhawk label
5. Report     corrected pass rates with error ranges  evalhawk report
6. Compare    versions: better / worse / can't tell   evalhawk compare
```

Steps 4–6 are what make EvalHawk different. They're described once in
[The trust layer](trust-layer.md) and apply to **every** system type.

## A draft of the config format

All pages use the same config shape (`evalhawk.toml`):

```toml
[target]                 # how to call your system (see architecture §5.1)
type = "http"            # or "callable", "openai_compatible", "recorded"

[[criteria]]             # a custom question
id       = "polite"
question = "Is the answer polite and professional?"

[[criteria]]             # a built-in template
id       = "answer_relevance"
template = "answer_relevance"

[[criteria]]             # a code check: no judge needed
id    = "under_150_words"
check = { type = "max_words", value = 150 }

[evaluations.support]
dataset  = "data/support.jsonl"
kind     = "single_turn"
criteria = { polite = "local", answer_relevance = "local", under_150_words = "code" }
```

`"local"` names a judge defined under `[judges.local]`; `"code"` means the criterion is a
code check. See [architecture §10](../architecture.md#10-configuration-and-public-api) for
judges and runner options.

## Using DeepEval metrics instead

If you already use DeepEval, keep your metrics. EvalHawk reads their results, treats
`score ≥ threshold` as PASS, and then applies the trust layer: checking against your
labels, a corrected pass rate, error ranges and version comparison. See
[Features](../features.md) for how the two tools fit together.
