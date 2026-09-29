# Features and how EvalHawk compares

!!! info "Planned"
    A summary of what EvalHawk will offer. For how each system type is tested, see
    [Evaluating AI systems](evals/index.md). DeepEval information was checked against its
    documentation on 2026-09-27; ❌ means "not found in their docs".

## The three layers

```
┌───────────────────────────────────────────────────────────────┐
│ 3. COMPARISON   Is v2 better? better / worse / can't tell + need N │
├───────────────────────────────────────────────────────────────┤
│ 2. TRUST        judge vs human check, corrected score, error ranges │
├───────────────────────────────────────────────────────────────┤
│ 1. EVALS        EvalHawk's own checks, or DeepEval's metrics        │
└───────────────────────────────────────────────────────────────┘
```

**DeepEval asks "what's the score?". EvalHawk asks "what's the *true* score, how sure are
we, and did it really change?"**, for its own evals and for DeepEval's.

## Layer 1: evals by system type

| System | EvalHawk evals | Research source | DeepEval equivalent | Phase |
|---|---|---|---|---|
| [Chatbot / Q&A](evals/chatbots.md) | Custom question, `answer_relevance`, `correctness`, format checks | G-Eval; RAGAS; MT-Bench | G-Eval, Answer Relevancy | 4 |
| [RAG](evals/rag.md) | `faithfulness` (supported, not just uncontradicted), `context_relevance`, `context_recall`, hit@k / recall@k / MRR / nDCG | FActScore; RAGAS; Järvelin & Kekäläinen (2002) | Faithfulness, Contextual Relevancy / Precision / Recall | 4 / 8 |
| [Summarization](evals/summarization.md) | `summary/faithfulness`, `summary/coverage` | FActScore; QAGS | Summarization | 4 / 8 |
| [Classification and extraction](evals/classification.md) | `exact_match`, `one_of`, `field_match`, `regex` | Standard | Custom code | 4 |
| [Structured output](evals/structured-output.md) | `valid_json`, `json_schema`, `field_match` | JSON Schema | JSON Correctness | 4 |
| [Agents](evals/agents.md) | `task_completed`, repeats with clustered ranges, pass^k; later tool and step checks | τ-bench; Berkeley Function-Calling Leaderboard | Task Completion, Tool / Argument Correctness, Step Efficiency, Plan Adherence / Quality | 4 / later |
| [Conversations](evals/conversations.md) | Remembers context, stays in role, resolved | MT-Bench | Knowledge Retention, Role Adherence, Conversation Completeness / Relevancy | Later |
| [Safety](evals/safety.md) | `safety/harmful`, `safety/toxic`, `safety/pii`, custom | Llama Guard taxonomy | Bias, Toxicity, PII Leakage, Misuse, Non-Advice, Role Violation | 4 |
| Head-to-head | Pairwise preference, both orders | MT-Bench / Chatbot Arena | Arena G-Eval | Later |
| Images | Not planned | — | Five image metrics | — |
| Bring your own | Import pass/fail files; DeepEval metrics; your own function | — | n/a | 3–4 |

**Where DeepEval is ahead:** breadth (agent steps, conversations, safety, images, red-teaming)
and maturity. EvalHawk doesn't try to match that; it works alongside it.

## Layers 2 and 3: what EvalHawk adds

| Feature | What you get | Method | DeepEval (open source) | Confident AI (cloud) | EvalHawk |
|---|---|---|---|---|---|
| Judge vs human check | "This judge wrongly passes 40% of bad answers" | Sensitivity, specificity, Cohen's kappa | ❌ | ✅ agreement breakdown | ✅ with error ranges |
| Corrected score | "Judge says 82% → really 76%" | Rogan-Gladen; PPI | ❌ | ❌ | ✅ |
| Error range on every number | "76% [70–82%]" | Wilson; bootstrap | ❌ | ⚠ not in their docs | ✅ |
| Related and repeated inputs | Honest, wider ranges | Clustered errors | ❌ | ❌ | ✅ |
| Version verdict | BETTER / WORSE / CAN'T TELL | McNemar; paired bootstrap | ❌ | Per-case regressions | ✅ statistical |
| How much more data | "Need ~900 more examples" | Power analysis | ❌ | ❌ | ✅ |
| Blind human labeling | The judge's verdict is hidden | Anchoring bias (EvalGen) | ❌ | Annotation, blind not stated | ✅ |
| Locked test sets | Can't tune on the test set by accident | Hash-based immutable splits | ❌ | ❌ | ✅ |
| Unbiased smart labeling | Useful items first, results stay fair | Inverse-probability weighting | ❌ | ❌ | ✅ |
| Judge confidence check | "90% sure → right 90% of the time?" | ECE, Brier, Platt, isotonic | ❌ | ❌ | ✅ |
| Cheap judge + backup | Pay for the strong judge only when needed | Cascades with a dev-tuned threshold | JEV metric ✅, cascade ❌ | ❌ | ✅ |
| Published accuracy of built-in evals | "Our faithfulness check catches X% of made-up facts" | Measured on public human-labelled data | ❌ | ❌ | ✅ |
| Footprint | — | — | 31 dependencies, telemetry library | Cloud service | 3 dependencies, local, no telemetry |

## Where the metrics come from

Most metrics in DeepEval and Ragas come from research ideas, but tools implement them
differently. "Answer relevancy" in the RAGAS paper generates questions from the answer and
compares embeddings; DeepEval's classifies statements. Same name, different numbers.

EvalHawk implements each eval **from the paper, with its own prompts**, documents the exact
method on the eval's page, cites the source, and measures its accuracy against human
labels. DeepEval and Ragas are Apache-2.0; if code or prompts are ever reused, their notices
are kept and changes are marked.

## Key papers

| Paper | Contribution |
|---|---|
| [G-Eval](https://arxiv.org/abs/2303.16634) (Liu et al., 2023) | AI judges scoring against criteria |
| [RAGAS](https://arxiv.org/abs/2309.15217) (Es et al., 2023) | RAG metrics: faithfulness, answer and context relevance |
| [FActScore](https://arxiv.org/abs/2305.14251) (Min et al., 2023) | Split into claims, check each one |
| [MT-Bench](https://arxiv.org/abs/2306.05685) (Zheng et al., 2023) | Judge biases; pairwise and reference-guided judging |
| [QAGS](https://arxiv.org/abs/2004.04228) (Wang et al., 2020) | Question-answering checks for summaries |
| [τ-bench](https://arxiv.org/abs/2406.12045) (Yao et al., 2024) | Agent reliability across repeated runs (pass^k) |
| [Llama Guard](https://arxiv.org/abs/2312.06674) (Inan et al., 2023) | Harm-category taxonomy |
| [Prediction-powered inference](https://arxiv.org/abs/2301.09633) (Angelopoulos et al., 2023) | Correcting estimates using a model plus a few labels |
| [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640) (Miller, 2024) | Error ranges, clustering, power for AI evals |
| [EvalGen](https://arxiv.org/abs/2404.12272) (Shankar et al., 2024) | Criteria drift; validating the validators |
