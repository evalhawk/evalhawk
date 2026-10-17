"""Convert MT-Bench human judgments into EvalHawk recorded-outcome JSONL (card X2).

Source: the public ``lmsys/mt_bench_human_judgments`` dataset on Hugging Face (CC-BY-4.0),
from Zheng et al. (2023), *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*.
Question categories come from FastChat's ``question.jsonl`` (Apache-2.0).

Each MT-Bench judgment answers "which answer is better, A or B?" for one question, one
pair of models and one conversation turn. EvalHawk's criteria are yes/no, so each pair is
put in alphabetical order and the criterion becomes:

    "Is the first model's answer better than the second model's answer?"

* GPT-4's verdict becomes the **judge** outcome; each human's verdict becomes a **label**.
* Every kind of tie becomes UNKNOWN. GPT-4's "tie (inconsistent)" means its verdict
  flipped when the answer order was swapped (position bias), so it isn't a real verdict.
* Turn 1 and turn 2 of the same (question, pair) share a ``group_id``: they are related.

Usage::

    uv run python experiments/datasets/mtbench_human.py --out data/mtbench_human.jsonl
    uv run evalhawk import data/mtbench_human.jsonl --target-version mtbench-2023 \\
        --db data/mtbench.db --criterion first_model_better \\
        --question "Is the first model's answer better than the second model's answer?" \\
        --judge-id gpt-4-pair-2023

Downloads are cached (default ``.evalhawk/datasets/mtbench``), so they happen once.
Standard library only: no new dependencies.
"""

import argparse
import json
import time
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from evalhawk.core.models import Outcome

DATASET = "lmsys/mt_bench_human_judgments"
ROWS_API = "https://datasets-server.huggingface.co/rows"
QUESTIONS_URL = (
    "https://raw.githubusercontent.com/lm-sys/FastChat/main/"
    "fastchat/llm_judge/data/mt_bench/question.jsonl"
)

CRITERION_NAME = "first_model_better"
CRITERION_QUESTION = "Is the first model's answer better than the second model's answer?"
JUDGE_ID = "gpt-4-pair-2023"
# The dataset has no annotation timestamps. One fixed, documented time keeps label
# identities stable across re-imports (EvalHawk uses created_at for label history).
LABEL_TIME = "2023-06-22T00:00:00Z"

Row = Mapping[str, Any]
UnitKey = tuple[int, str, str, int]  # (question_id, first model, second model, turn)


def orient(model_a: str, model_b: str, winner: str) -> tuple[str, str, Outcome]:
    """Put a pair in alphabetical order and express the winner as PASS/FAIL/UNKNOWN.

    PASS means the alphabetically first model's answer is better; FAIL means the second
    model's is; every kind of tie is UNKNOWN.
    """
    if model_a == model_b:
        raise ValueError(f"a pair needs two different models, got {model_a!r} twice")
    first, second = sorted((model_a, model_b))
    if winner.startswith("tie"):
        return first, second, Outcome.UNKNOWN
    if winner not in ("model_a", "model_b"):
        raise ValueError(f"unrecognised winner {winner!r}; expected model_a, model_b or tie")
    winning_model = model_a if winner == "model_a" else model_b
    return first, second, Outcome.PASS if winning_model == first else Outcome.FAIL


def _unit(row: Row) -> tuple[UnitKey, Outcome]:
    first, second, outcome = orient(str(row["model_a"]), str(row["model_b"]), str(row["winner"]))
    return (int(row["question_id"]), first, second, int(row["turn"])), outcome


def _answer(row: Row, model: str, turn: int) -> str:
    """The model's assistant message for ``turn`` (1-based) in either conversation."""
    conversation = row["conversation_a"] if row["model_a"] == model else row["conversation_b"]
    assistant = [message["content"] for message in conversation if message["role"] == "assistant"]
    return str(assistant[turn - 1])


def _prompt(row: Row, turn: int) -> list[str]:
    users = [message["content"] for message in row["conversation_a"] if message["role"] == "user"]
    return [str(text) for text in users[:turn]]


def build_rows(
    gpt4_rows: Iterable[Row], human_rows: Iterable[Row], *, categories: Mapping[int, str]
) -> list[dict[str, Any]]:
    """One EvalHawk row per unit judged by GPT-4, with all human labels for that unit."""
    gpt4: dict[UnitKey, tuple[Row, Outcome]] = {}
    for row in gpt4_rows:
        key, outcome = _unit(row)
        if key in gpt4:
            raise ValueError(f"more than one GPT-4 verdict for {key}")
        gpt4[key] = (row, outcome)

    labels: defaultdict[UnitKey, list[dict[str, str]]] = defaultdict(list)
    for row in human_rows:
        key, outcome = _unit(row)
        labels[key].append(
            {"annotator": str(row["judge"]), "outcome": outcome.value, "created_at": LABEL_TIME}
        )

    out: list[dict[str, Any]] = []
    for key in sorted(gpt4):
        question_id, first, second, turn = key
        row, outcome = gpt4[key]
        pair = f"{first}_vs_{second}"
        out.append(
            {
                "input": {
                    "question_id": question_id,
                    "turn": turn,
                    "models": [first, second],
                    "prompt": _prompt(row, turn),
                },
                "output": (
                    f"[Answer from {first}]\n{_answer(row, first, turn)}\n\n"
                    f"[Answer from {second}]\n{_answer(row, second, turn)}"
                ),
                "group_id": f"q{question_id}-{pair}",
                "tags": [categories[question_id], pair],
                "judge": outcome.value,
                "labels": sorted(labels.get(key, []), key=lambda label: label["annotator"]),
                "metadata": {"source": DATASET, "gpt4_winner_raw": str(row["winner"])},
            }
        )
    return out


def write_jsonl(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    """Write rows as UTF-8 JSONL with LF line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------- downloading
def _get_json(url: str) -> Any:
    """GET JSON, backing off politely on HTTP 429 (the API rate-limits bursts)."""
    delay = 5.0
    for _ in range(8):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                raise
            time.sleep(float(exc.headers.get("Retry-After") or delay))
            delay *= 2
    raise RuntimeError(f"{url}: still rate-limited after 8 attempts; try again later")


def download_split(split: str, cache_dir: Path) -> list[dict[str, Any]]:
    """All rows of one dataset split, cached as JSON after the first download."""
    cached = cache_dir / f"{split}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    while True:
        page = _get_json(
            f"{ROWS_API}?dataset={DATASET.replace('/', '%2F')}&config=default"
            f"&split={split}&offset={len(rows)}&length=100"
        )
        batch = [item["row"] for item in page["rows"]]
        rows.extend(batch)
        if not batch or len(rows) >= page["num_rows_total"]:
            break
        time.sleep(1.5)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def download_categories(cache_dir: Path) -> dict[int, str]:
    """question_id → category (writing, roleplay, reasoning, math, coding, ...)."""
    cached = cache_dir / "question.jsonl"
    if not cached.exists():
        with urllib.request.urlopen(QUESTIONS_URL, timeout=60) as response:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(response.read())
    lines = cached.read_text(encoding="utf-8").splitlines()
    return {
        int(item["question_id"]): str(item["category"])
        for item in (json.loads(line) for line in lines if line.strip())
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert MT-Bench human judgments into EvalHawk recorded-outcome JSONL."
    )
    parser.add_argument("--out", type=Path, default=Path("data/mtbench_human.jsonl"))
    parser.add_argument("--cache-dir", type=Path, default=Path(".evalhawk/datasets/mtbench"))
    args = parser.parse_args(argv)

    categories = download_categories(args.cache_dir)
    human = download_split("human", args.cache_dir)
    gpt4 = download_split("gpt4_pair", args.cache_dir)
    rows = build_rows(gpt4, human, categories=categories)
    write_jsonl(rows, args.out)

    labelled = sum(1 for row in rows if row["labels"])
    print(f"Wrote {len(rows)} rows to {args.out} ({labelled} with human labels).")
    print(f"Criterion: {CRITERION_NAME!r} = {CRITERION_QUESTION!r}; judge ID {JUDGE_ID!r}.")


if __name__ == "__main__":
    main()
