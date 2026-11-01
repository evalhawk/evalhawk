import pytest

from evalhawk.core.models import Outcome
from evalhawk.judges.criteria import BUILTIN_CRITERIA, builtin_criterion
from evalhawk.judges.parsing import parse_verdict


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The claims are supported.\nVERDICT: PASS", Outcome.PASS),
        ("verdict: fail", Outcome.FAIL),
        ("VERDICT = UNKNOWN", Outcome.UNKNOWN),
        ("**VERDICT: PASS**", Outcome.PASS),
        ("PASS", Outcome.PASS),
        ("  fail. ", Outcome.FAIL),
    ],
)
def test_parse_accepts_the_documented_forms(text: str, expected: Outcome) -> None:
    outcome, _, parsed = parse_verdict(text)
    assert outcome is expected
    assert parsed


def test_last_verdict_line_wins_and_reasoning_is_kept() -> None:
    text = "At first I thought VERDICT: PASS, but claim 2 is unsupported.\nVERDICT: FAIL"
    outcome, reasoning, _ = parse_verdict(text)
    assert outcome is Outcome.FAIL
    assert reasoning is not None
    assert "claim 2 is unsupported" in reasoning


@pytest.mark.parametrize("text", ["", "It seems fine overall.", "PASS or FAIL, hard to say"])
def test_unreadable_replies_become_unknown_never_a_guess(text: str) -> None:
    outcome, reasoning, parsed = parse_verdict(text)
    assert outcome is Outcome.UNKNOWN
    assert not parsed
    assert reasoning is not None
    assert reasoning.startswith("Unparseable")


def test_builtin_library_is_complete_and_consistent() -> None:
    assert {
        "answer_relevance",
        "correctness",
        "faithfulness",
        "context_relevance",
        "context_recall",
        "summary_faithfulness",
        "summary_coverage",
        "safety_harmful",
        "safety_toxic",
        "task_completed",
        "instruction_following",
    } <= set(BUILTIN_CRITERIA)
    for name, item in BUILTIN_CRITERIA.items():
        assert item.name == name
        assert item.question.endswith("?")  # one yes/no question each
        assert item.guidance
        assert item.source
        assert item.criterion().name == name


def test_rag_builtins_declare_their_data_needs() -> None:
    assert builtin_criterion("faithfulness").needs_contexts
    assert builtin_criterion("context_recall").needs_reference
    assert builtin_criterion("correctness").needs_reference
    assert not builtin_criterion("answer_relevance").needs_contexts


def test_unknown_builtin_lists_the_options() -> None:
    with pytest.raises(KeyError, match="available: answer_relevance"):
        builtin_criterion("helpfulness")
