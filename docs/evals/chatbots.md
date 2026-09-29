# Chatbots and Q&A

!!! info "Planned: Phase 4"

## What it covers

Any system that takes **one message** and returns **one answer**: support bots, internal
assistants, FAQ bots, "ask the model" features. For bots that retrieve documents first,
also read [RAG systems](rag.md). For whole conversations, see [Conversations](conversations.md).

## What can go wrong

| Failure | Example |
|---|---|
| Doesn't answer the question | Asked about refunds, talks about shipping |
| Wrong answer | "Refunds within 60 days" when it's 30 |
| Makes things up | Invents a loyalty programme |
| Wrong tone | Curt or sarcastic with an upset customer |
| Ignores instructions | Too long, wrong language, uses markdown where it shouldn't |

Each failure you care about becomes **one criterion**.

## The evals

| Eval | Question it asks | How it works | Needs | Based on |
|---|---|---|---|---|
| `answer_relevance` (template) | Does the answer address what was asked? | AI judge, one yes/no verdict | `input`, `output` | [RAGAS](https://arxiv.org/abs/2309.15217) (Es et al., 2023) |
| `correctness` (template) | Does the answer agree with the reference answer? | AI judge compares against the reference | `reference` | Reference-guided judging, [MT-Bench](https://arxiv.org/abs/2306.05685) (Zheng et al., 2023) |
| Custom question | Anything you write, e.g. "Is the tone empathetic?" | AI judge, one yes/no verdict | `input`, `output` | [G-Eval](https://arxiv.org/abs/2303.16634) (Liu et al., 2023), made binary |
| `max_words`, `contains`, `regex`, `language` (code) | Format and instruction rules | Code, no AI | `output` | — |

**Tips for custom questions:**

- One failure per question. "Is it accurate and polite?" is two criteria.
- Phrase it so PASS means good: "Is the answer free of made-up facts?"
- Avoid rewarding length. "Is it helpful?" tends to favour long answers.

## What you provide

A JSONL file with one test input per line:

```json
{"input": "What's your refund policy?", "reference": "Refunds within 30 days of purchase."}
{"input": "Do you ship to Canada?", "reference": "Yes, 5–7 business days.", "group_id": "shipping"}
```

- `reference` is optional (only `correctness` needs it).
- `group_id` is optional: use it for related questions, so the error ranges stay honest.

Your chatbot is called through a [target](../architecture.md#51-built-in-targets-phase-3):
a Python function, an HTTP endpoint, or an OpenAI-compatible model. If you already have
the answers, add an `"output"` field and use the `recorded` target.

## How it's tested

1. EvalHawk checks the file (every row has an `input`; `reference` exists if `correctness` is used).
2. It assigns each input to train, dev or test, and locks the assignment.
3. It sends each input to your chatbot and stores the answer.
4. Each answer is checked against each criterion. Code checks run instantly; AI-judged
   criteria are sent to the judge, and results are cached.
5. You label about 100 answers per AI-judged criterion (`evalhawk label`).
6. The report shows corrected pass rates with error ranges ([The trust layer](trust-layer.md)).

## Example config

```toml
[target]
type    = "http"
url     = "https://bot.internal/api/chat"
body    = '{"message": "{{input}}"}'
answer_path = "$.reply"

[[criteria]]
id       = "answer_relevance"
template = "answer_relevance"

[[criteria]]
id       = "correctness"
template = "correctness"

[[criteria]]
id       = "empathetic"
question = "If the customer sounds upset, does the answer acknowledge it?"

[[criteria]]
id    = "concise"
check = { type = "max_words", value = 150 }

[evaluations.support]
dataset  = "data/support.jsonl"
kind     = "single_turn"
criteria = { answer_relevance = "local", correctness = "local", empathetic = "local", concise = "code" }
```

## What you get

Illustrative output:

```text
evaluation: support    run: v2    n = 500    judge: local

criterion          pass rate (corrected)    judge says   judge status      unknown
answer_relevance   91%  [88% – 94%]         93%          ✅ ok (n=100)      0.4%
correctness        78%  [73% – 83%]         84%          ✅ ok (n=120)      1.2%
empathetic         64%  [55% – 72%]         70%          ⚠ need ~40 more    2.0%
concise            97%  [95% – 98%]         code check   —                  —
```

## Compared with DeepEval

| | DeepEval | EvalHawk |
|---|---|---|
| Relevance | Answer Relevancy: share of relevant statements, 0–1, pass at ≥ 0.5 | One yes/no verdict per answer |
| Custom criteria | G-Eval: a 0–1 score from weighted ratings | A yes/no custom question |
| Result | Scores per test case, pass/fail per threshold | Corrected pass rate with an error range, plus a judge report card |
