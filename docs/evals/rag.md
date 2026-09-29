# RAG systems

!!! info "Planned: Phase 4 (answer checks), Phase 8 (retrieval checks and published accuracy)"

## What it covers

Systems that **retrieve** documents and then **generate** an answer from them: "ask our
docs" bots, support bots grounded in a knowledge base, research assistants.

A RAG system has two parts that fail in different ways, so they're tested separately:

```
question ──► RETRIEVER ──► documents ──► GENERATOR ──► answer
             "did we find the           "did we use them
              right documents?"          faithfully?"
```

## What can go wrong

| Part | Failure | Example |
|---|---|---|
| Generator | Makes up facts not in the documents | Documents say 30 days; answer adds "refunds go to your original card" |
| Generator | Ignores the question | Correct facts, wrong topic |
| Retriever | Retrieves irrelevant documents | Question about refunds, retrieves the shipping page |
| Retriever | Misses a document it needed | Finds the refund page but not the exceptions page |

## The evals

**Generator checks:**

| Eval | Question it asks | How it works | Needs | Based on |
|---|---|---|---|---|
| `faithfulness` | Is **every** claim in the answer **supported** by the retrieved documents? | 1. The judge splits the answer into claims. 2. It checks each claim against the documents. 3. PASS only if all claims are supported | `output`, `contexts` | [FActScore](https://arxiv.org/abs/2305.14251) (Min et al., 2023); [RAGAS](https://arxiv.org/abs/2309.15217) |
| `answer_relevance` | Does the answer address the question? | One yes/no verdict | `input`, `output` | RAGAS |

**Retriever checks:**

| Eval | Question it asks | How it works | Needs | Based on |
|---|---|---|---|---|
| `context_relevance` | Are the retrieved documents relevant to the question? | The judge checks each document; PASS if the relevant share meets your minimum | `input`, `contexts` | RAGAS |
| `context_recall` | Do the documents contain everything needed for the reference answer? | The judge splits the reference into facts and checks each is in the documents | `contexts`, `reference` | RAGAS |
| `hit@k`, `recall@k`, `MRR`, `nDCG@k` | Did the right documents appear, and how high? | Pure math, no AI | `retrieved_ids`, `relevant_ids` | Standard information retrieval; nDCG: Järvelin & Kekäläinen (2002) |

**Why our faithfulness is stricter than DeepEval's.** DeepEval counts a claim as faithful if
it doesn't **contradict** the documents, so a claim the documents never mention still counts
as faithful. EvalHawk requires each claim to be **supported**. In the example above,
"refunds go to your original card" **fails** in EvalHawk.

A claim-level breakdown is stored as the verdict's reasoning, so you can see which claim failed.

## What you provide

```json
{"input": "What's your refund policy?", "reference": "Refunds within 30 days; shipping isn't refunded.", "relevant_ids": ["doc-refunds"]}
```

Your system's response must include the retrieved documents. With an HTTP target, point
`contexts_path` at them; for pre-recorded data, add them per row:

```json
{"input": "...", "output": "...", "contexts": ["Refunds within 30 days...", "Shipping costs..."], "retrieved_ids": ["doc-refunds", "doc-shipping"]}
```

## How it's tested

1. The data-shape check makes sure every row has `contexts` (and `reference` or
   `relevant_ids` if the chosen evals need them). A missing field fails **before** any
   paid call, naming the row.
2. The retrieval math (`hit@k` and the rest) runs instantly with no judge.
3. The generator and retriever criteria are judged by AI and cached.
4. You label about 100 answers for `faithfulness`. It's the criterion where judges are
   most often wrong, so it matters most.
5. The report shows retriever and generator results separately, so you know **which part** to fix.

## Example config

```toml
[target]
type          = "http"
url           = "https://docs-bot.internal/ask"
body          = '{"q": "{{input}}"}'
answer_path   = "$.answer"
contexts_path = "$.sources[*].text"

[[criteria]]
id       = "faithfulness"
template = "rag/faithfulness"

[[criteria]]
id       = "context_relevance"
template = "rag/context_relevance"

[evaluations.docs_bot]
dataset  = "data/docs_questions.jsonl"
kind     = "rag"
criteria = { faithfulness = "local", context_relevance = "local" }
```

## What you get

Illustrative output:

```text
evaluation: docs_bot    run: v3    n = 400

RETRIEVER
  hit@5                  88%  [84% – 91%]      code
  context_relevance      81%  [76% – 86%]      judge ✅ ok

GENERATOR
  faithfulness           72%  [66% – 78%]      judge says 85%   ✅ ok (n=150)
  answer_relevance       93%  [90% – 95%]      judge ✅ ok
```

Here the judge over-reported faithfulness by 13 points, and the corrected figure shows
the generator is the part to fix.

## Published accuracy (Phase 8)

We'll measure EvalHawk's own `faithfulness` judge against RAGTruth, a public dataset with
human labels for made-up content, and publish its sensitivity and specificity with error
ranges. You'll know how good the built-in check is before you rely on it.

## Compared with DeepEval

| | DeepEval | EvalHawk |
|---|---|---|
| Faithfulness rule | Claim is faithful if **not contradicted** | Claim must be **supported** |
| Score | Share of faithful claims (0–1), pass at ≥ 0.5 | PASS only if every claim is supported |
| Retrieval ranking metrics | Contextual Precision (AI-judged) | Also code-based hit@k, recall@k, MRR, nDCG |
| Accuracy of the metric itself | Not published | Measured on RAGTruth and published |
