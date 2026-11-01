# Examples

Each folder is a self-contained project: `cd` into it and run the commands below. All run
offline, with no API key, and are exercised by `tests/integration/test_examples.py`.

| Folder | Shows | Run |
|---|---|---|
| [`rag-support`](rag-support) | RAG target returning contexts and retrieved IDs, a custom Python judge, retrieval metrics | `evalhawk eval -t v1` then `evalhawk retrieval --run v1 --k 2` |
| [`ci`](ci) | A GitHub workflow that blocks PRs on a significant regression | copy `evalhawk-gate.yml` to `.github/workflows/` |

For the smallest possible start, run `evalhawk init my-bot`.

The RAG example's bot is deliberately flawed: two questions retrieve nothing relevant
(hit@2 = 0.778) and one answer invents a "5 points per dollar" loyalty programme, which the
`grounded_numbers` judge catches (90% pass). With only 10 questions, notice how wide every
interval is.
