"""Tests for the MT-Bench human-judgments converter (card X2).

The converter turns pairwise MT-Bench judgments ("which answer is better, A or B?")
into EvalHawk's recorded-outcome JSONL: one row per (question, model pair, turn),
GPT-4's verdict as the judge, and each human's verdict as a label.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from evalhawk.core.models import Criterion, Outcome, Run
from evalhawk.sources.verdicts import VerdictSource

ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    path = ROOT / "experiments" / "datasets" / "mtbench_human.py"
    spec = importlib.util.spec_from_file_location("mtbench_human", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mt = _load()


def _conv(model: str) -> list[dict[str, str]]:
    return [
        {"role": "user", "content": "Q turn 1"},
        {"role": "assistant", "content": f"{model} answer 1"},
        {"role": "user", "content": "Q turn 2"},
        {"role": "assistant", "content": f"{model} answer 2"},
    ]


def _row(
    a: str, b: str, winner: str, judge: str, turn: int = 1, qid: int = 81
) -> dict[str, object]:
    return {
        "question_id": qid,
        "model_a": a,
        "model_b": b,
        "winner": winner,
        "judge": judge,
        "conversation_a": _conv(a),
        "conversation_b": _conv(b),
        "turn": turn,
    }


# ------------------------------------------------------------------ orientation
def test_pair_is_always_put_in_alphabetical_order() -> None:
    assert mt.orient("gpt-4", "claude-v1", "model_a") == ("claude-v1", "gpt-4", Outcome.FAIL)
    assert mt.orient("claude-v1", "gpt-4", "model_b") == ("claude-v1", "gpt-4", Outcome.FAIL)


def test_first_model_winning_is_pass() -> None:
    assert mt.orient("claude-v1", "gpt-4", "model_a")[2] is Outcome.PASS
    assert mt.orient("gpt-4", "claude-v1", "model_b")[2] is Outcome.PASS


@pytest.mark.parametrize("tie", ["tie", "tie (inconsistent)", "tie (bothbad)"])
def test_every_kind_of_tie_is_unknown(tie: str) -> None:
    assert mt.orient("claude-v1", "gpt-4", tie)[2] is Outcome.UNKNOWN


def test_unrecognised_winner_is_refused() -> None:
    with pytest.raises(ValueError, match="winner"):
        mt.orient("claude-v1", "gpt-4", "both")


def test_same_model_twice_is_refused() -> None:
    with pytest.raises(ValueError, match="different models"):
        mt.orient("gpt-4", "gpt-4", "model_a")


# --------------------------------------------------------------------- one row
def test_human_and_gpt4_in_opposite_orders_land_on_the_same_unit() -> None:
    gpt4 = [_row("gpt-4", "claude-v1", "model_a", "gpt4_pair")]  # GPT-4: gpt-4 wins
    human = [_row("claude-v1", "gpt-4", "model_b", "author_1")]  # human: gpt-4 wins
    rows = mt.build_rows(gpt4, human, categories={81: "writing"})
    assert len(rows) == 1
    row = rows[0]
    assert row["judge"] == "FAIL"  # first model (claude-v1) did NOT win
    assert [label["outcome"] for label in row["labels"]] == ["FAIL"]  # human agrees


def test_row_contents() -> None:
    gpt4 = [_row("claude-v1", "gpt-4", "tie (inconsistent)", "gpt4_pair", turn=2)]
    human = [
        _row("claude-v1", "gpt-4", "model_a", "author_1", turn=2),
        _row("gpt-4", "claude-v1", "model_a", "author_2", turn=2),
    ]
    (row,) = mt.build_rows(gpt4, human, categories={81: "writing"})
    assert row["input"] == {
        "question_id": 81,
        "turn": 2,
        "models": ["claude-v1", "gpt-4"],
        "prompt": ["Q turn 1", "Q turn 2"],
    }
    assert "claude-v1 answer 2" in row["output"]
    assert "gpt-4 answer 2" in row["output"]
    assert row["output"].index("claude-v1") < row["output"].index("gpt-4")
    assert row["group_id"] == "q81-claude-v1_vs_gpt-4"
    assert row["tags"] == ["writing", "claude-v1_vs_gpt-4"]
    assert row["judge"] == "UNKNOWN"  # GPT-4 was position-inconsistent
    assert {(lab["annotator"], lab["outcome"]) for lab in row["labels"]} == {
        ("author_1", "PASS"),
        ("author_2", "FAIL"),
    }
    assert row["metadata"]["gpt4_winner_raw"] == "tie (inconsistent)"


def test_units_without_a_gpt4_verdict_are_skipped() -> None:
    human = [_row("claude-v1", "gpt-4", "model_a", "author_1")]
    assert mt.build_rows([], human, categories={81: "writing"}) == []


def test_duplicate_gpt4_verdicts_are_refused() -> None:
    gpt4 = [_row("claude-v1", "gpt-4", "model_a", "gpt4_pair")] * 2
    with pytest.raises(ValueError, match="more than one GPT-4"):
        mt.build_rows(gpt4, [], categories={81: "writing"})


def test_rows_are_in_a_stable_order() -> None:
    gpt4 = [
        _row("claude-v1", "gpt-4", "model_a", "gpt4_pair", qid=82),
        _row("alpaca-13b", "gpt-4", "model_a", "gpt4_pair", qid=81, turn=2),
        _row("alpaca-13b", "gpt-4", "model_a", "gpt4_pair", qid=81, turn=1),
    ]
    rows = mt.build_rows(gpt4, [], categories={81: "writing", 82: "writing"})
    assert [(r["input"]["question_id"], r["input"]["turn"]) for r in rows] == [
        (81, 1),
        (81, 2),
        (82, 1),
    ]


# ------------------------------------------------- works with EvalHawk's importer
def test_written_file_is_accepted_by_the_evalhawk_importer(tmp_path: Path) -> None:
    gpt4 = [_row("claude-v1", "gpt-4", "model_b", "gpt4_pair")]
    human = [_row("gpt-4", "claude-v1", "model_a", "author_3")]
    path = tmp_path / "mtbench.jsonl"
    mt.write_jsonl(mt.build_rows(gpt4, human, categories={81: "writing"}), path)

    run = Run(target_version="mtbench-2023")
    criterion = Criterion(name=mt.CRITERION_NAME, question=mt.CRITERION_QUESTION)
    (observation,) = VerdictSource(path, run=run, criterion=criterion, judge_id=mt.JUDGE_ID).load()
    assert observation.verdict.outcome is Outcome.FAIL
    assert [label.outcome for label in observation.labels] == [Outcome.FAIL]
    assert observation.example.group_id == "q81-claude-v1_vs_gpt-4"
    json.loads(path.read_text(encoding="utf-8").splitlines()[0])  # valid JSON line
