import asyncio

import pytest

from evalhawk.core.models import Criterion, Example, Outcome, Trace
from evalhawk.judges.code import CodeCheckJudge, schema_errors

CRITERION = Criterion(name="check", question="Does the output pass the check?")


def _run(output: str, check: str, reference: object = None, **options: object) -> Outcome:
    example = Example.model_validate({"input": "q", "reference": reference})
    trace = Trace(example_id=example.id, run_id="run", output=output)
    verdict = asyncio.run(CodeCheckJudge(check, **options).judge(example, trace, CRITERION))
    assert verdict.reasoning
    return verdict.outcome


@pytest.mark.parametrize(
    ("output", "reference", "options", "expected"),
    [
        ("billing", "billing", {}, Outcome.PASS),
        ("  billing ", "billing", {}, Outcome.PASS),  # whitespace normalised by default
        ("Billing", "billing", {}, Outcome.FAIL),
        ("Billing!", "billing", {"normalise": ["case", "punctuation"]}, Outcome.PASS),
        ("anything", None, {}, Outcome.UNKNOWN),  # no reference: can't decide
    ],
)
def test_exact_match(
    output: str, reference: str | None, options: dict[str, object], expected: Outcome
) -> None:
    assert _run(output, "exact_match", reference, **options) is expected


def test_text_checks() -> None:
    assert _run("Refunds within 30 days", "contains", value="30 DAYS") is Outcome.PASS
    assert (
        _run("Refunds within 30 days", "contains", value="30 DAYS", case_sensitive=True)
        is Outcome.FAIL
    )
    assert _run("Sorry, I can't help", "not_contains", value="sorry") is Outcome.FAIL
    assert _run("Order A-1042", "regex", pattern=r"[A-Z]-\d{4}") is Outcome.PASS
    assert _run("one two three", "max_words", value=3) is Outcome.PASS
    assert _run("one two three four", "max_words", value=3) is Outcome.FAIL
    assert _run("one two", "min_words", value=3) is Outcome.FAIL
    assert _run("abcdef", "max_chars", value=5) is Outcome.FAIL
    assert _run("   ", "not_empty") is Outcome.FAIL
    assert _run(" Billing ", "one_of", values=["billing", "technical"]) is Outcome.PASS
    assert _run("sales", "one_of", values=["billing", "technical"]) is Outcome.FAIL


def test_json_checks() -> None:
    schema = {
        "type": "object",
        "required": ["vendor", "total"],
        "properties": {"vendor": {"type": "string"}, "total": {"type": "number", "minimum": 0}},
        "additionalProperties": False,
    }
    assert _run('{"a": 1}', "valid_json") is Outcome.PASS
    assert _run('{"a": 1', "valid_json") is Outcome.FAIL
    assert _run('{"vendor": "ACME", "total": 12.5}', "json_schema", schema=schema) is Outcome.PASS
    assert _run('{"vendor": "ACME"}', "json_schema", schema=schema) is Outcome.FAIL
    assert _run('{"vendor": "ACME", "total": -1}', "json_schema", schema=schema) is Outcome.FAIL
    assert _run('{"vendor": 3, "total": 1}', "json_schema", schema=schema) is Outcome.FAIL
    assert _run("not json", "json_schema", schema=schema) is Outcome.FAIL
    ref = {"order": {"total": 59.0}}
    assert (
        _run('{"order": {"total": 59.0}}', "field_match", ref, field="order.total") is Outcome.PASS
    )
    assert _run('{"order": {"total": 60}}', "field_match", ref, field="order.total") is Outcome.FAIL
    assert _run('{"order": {}}', "field_match", ref, field="order.total") is Outcome.FAIL
    assert _run('{"x": 1}', "field_match", {"other": 1}, field="order.total") is Outcome.UNKNOWN


def test_schema_errors_explain_where() -> None:
    errors = schema_errors(
        {"items": [1, "two"]}, {"properties": {"items": {"items": {"type": "integer"}}}}
    )
    assert errors == ["$.items[1]: expected integer, got str"]
    assert schema_errors(True, {"type": "integer"}) == ["$: expected integer, got bool"]


def test_pii_check() -> None:
    assert _run("Contact jane.doe@example.com", "pii") is Outcome.FAIL
    assert _run("Call +44 20 7946 0958 today", "pii") is Outcome.FAIL
    assert _run("Card 4111 1111 1111 1111", "pii") is Outcome.FAIL
    assert _run("Your order ships in 3 days.", "pii") is Outcome.PASS
    assert _run("jane@example.com", "pii", patterns=["phone"]) is Outcome.PASS


def test_bad_configuration_fails_early() -> None:
    with pytest.raises(ValueError, match="unknown code check"):
        CodeCheckJudge("spellcheck")
    with pytest.raises(ValueError, match="needs option"):
        CodeCheckJudge("max_words")
    with pytest.raises(ValueError, match="PII"):
        CodeCheckJudge("pii", patterns=["passport"])
    with pytest.raises(Exception, match="unterminated|missing"):
        CodeCheckJudge("regex", pattern="(")


def test_judge_id_depends_on_check_and_options() -> None:
    assert (
        CodeCheckJudge("max_words", value=10).judge_id
        == CodeCheckJudge("max_words", value=10).judge_id
    )
    assert (
        CodeCheckJudge("max_words", value=10).judge_id
        != CodeCheckJudge("max_words", value=11).judge_id
    )
