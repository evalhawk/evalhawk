"""Synthetic support-bot fixtures with separately stored ground truth; no model calls."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from evalhawk.core.errors import DataError
from evalhawk.core.models import Example, Split
from evalhawk.core.splits import SplitSet


def generate_demo(
    directory: Path,
    *,
    seed: int = 0,
    cases: int = 1000,
    paraphrases: int = 3,
) -> None:
    """Generate three dependent paraphrases per independent case; dev labels only."""
    if cases < 300:
        raise DataError("demo needs at least 300 cases for calibration")
    if not 1 <= paraphrases <= 10:
        raise DataError("paraphrases must be between 1 and 10")
    names = ("v1.jsonl", "v2.jsonl", "answer_key.json")
    if any((directory / name).exists() for name in names):
        raise DataError("demo files already exist; choose a new directory")
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    splits = SplitSet()
    timestamp = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    tags = ("billing", "shipping", "account")
    pass_rates = ((0.74, 0.65, 0.65), (0.60, 0.82, 0.80))
    truths: dict[str, dict[str, list[int]]] = {
        version: {tag: [] for tag in tags} for version in ("v1", "v2")
    }
    with (
        (directory / "v1.jsonl").open("w", encoding="utf-8") as first,
        (directory / "v2.jsonl").open("w", encoding="utf-8") as second,
    ):
        for case in range(cases):
            tag_index = case % len(tags)
            tag = tags[tag_index]
            quality = rng.random()
            for version_index, stream in enumerate((first, second)):
                version = f"v{version_index + 1}"
                human = quality < pass_rates[version_index][tag_index]
                verdict = "PASS" if rng.random() < (0.92 if human else 0.40) else "FAIL"
                if rng.random() < 0.01:
                    verdict = "UNKNOWN"
                conflicted = rng.random() < 0.04
                for paraphrase in range(paraphrases):
                    example = Example(
                        input=f"Support case {case}: {tag} question, phrasing {paraphrase}",
                        reference="Resolve the customer's request according to policy.",
                        group_id=f"support-{case}",
                        tags=(tag,),
                    )
                    pile = splits.assign(example)
                    labels = []
                    if pile == Split.DEV:
                        outcome = "PASS" if human else "FAIL"
                        labels.append(
                            {
                                "annotator": "blind-reviewer-a",
                                "outcome": outcome,
                                "created_at": timestamp,
                            }
                        )
                        if conflicted:
                            labels.append(
                                {
                                    "annotator": "blind-reviewer-b",
                                    "outcome": "FAIL" if human else "PASS",
                                    "created_at": timestamp,
                                }
                            )
                    if pile == Split.TEST:
                        truths[version][tag].append(int(human))
                    record = {
                        "input": example.input,
                        "reference": example.reference,
                        "group_id": example.group_id,
                        "tags": example.tags,
                        "output": f"Synthetic {version} response to case {case}.",
                        "judge": verdict,
                        "labels": labels,
                    }
                    stream.write(json.dumps(record) + "\n")
    answer = {
        "synthetic": True,
        "seed": seed,
        "cases": cases,
        "judge_sensitivity": 0.92,
        "judge_specificity": 0.60,
        "test_truth": {
            version: {
                "overall": sum(sum(values) for values in by_tag.values())
                / sum(len(values) for values in by_tag.values()),
                "tags": {tag: sum(values) / len(values) for tag, values in by_tag.items()},
            }
            for version, by_tag in truths.items()
        },
    }
    (directory / "answer_key.json").write_text(
        json.dumps(answer, indent=2) + "\n", encoding="utf-8"
    )
