import asyncio

import pytest

from evalhawk.core.errors import CallError, DataError
from evalhawk.core.models import Example, TargetOutput
from evalhawk.targets.callable import CallableTarget, to_output
from evalhawk.targets.http import fill
from evalhawk.targets.recorded import RecordedTarget
from evalhawk.transport import jsonpath

DOC = {
    "reply": {"text": "Refunds within 30 days.", "sources": [{"text": "doc A"}, {"text": "doc B"}]},
    "choices": [{"message": {"content": "hi"}}],
    "odd key": 1,
}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("$.reply.text", ["Refunds within 30 days."]),
        ("$.reply.sources[*].text", ["doc A", "doc B"]),
        ("$.reply.sources[1].text", ["doc B"]),
        ("$.choices[0].message.content", ["hi"]),
        ('$["odd key"]', [1]),
        ("$.missing", []),
        ("$.reply.sources[9].text", []),
    ],
)
def test_jsonpath(path: str, expected: list[object]) -> None:
    assert jsonpath.find(DOC, path) == expected


@pytest.mark.parametrize("path", ["reply.text", "$.reply..text", "$.a[?(@.b)]"])
def test_unsupported_jsonpath_fails_at_config_time(path: str) -> None:
    with pytest.raises(ValueError, match="JSONPath"):
        jsonpath.validate(path)


def test_body_template_substitution() -> None:
    example = Example(input={"question": 'Say "hi"', "lang": "en"}, reference="hi")
    body = {
        "q": "{{input.question}}",
        "whole": "{{input}}",
        "text": "Answer in {{input.lang}}: {{input.question}}",
        "expected": "{{ reference }}",
        "n": 3,
    }
    assert fill(body, example) == {
        "q": 'Say "hi"',
        "whole": {"question": 'Say "hi"', "lang": "en"},  # whole placeholder keeps the object
        "text": 'Answer in en: Say "hi"',
        "expected": "hi",
        "n": 3,
    }
    with pytest.raises(CallError, match="no such field"):
        fill("{{input.missing}}", example)


def test_callable_target_sync_async_and_shapes() -> None:
    def sync_app(question: str) -> str:
        return question.upper()

    async def rag_app(question: str) -> dict[str, object]:
        return {"output": "answer", "contexts": ["d1", "d2"]}

    example = Example(input="hello")
    out = asyncio.run(CallableTarget(sync_app)(example))
    assert out.output == "HELLO"
    assert out.latency_ms >= 0
    rag = asyncio.run(CallableTarget(rag_app)(example))
    assert rag.contexts == ("d1", "d2")
    whole = asyncio.run(CallableTarget(lambda ex: ex.id, pass_example=True)(example))
    assert whole.output == example.id
    with pytest.raises(DataError, match="return a str"):
        to_output(42)


def test_recorded_target() -> None:
    example = Example(input="q")
    target = RecordedTarget.from_rows([(example, TargetOutput(output="stored"))])
    assert asyncio.run(target(example)).output == "stored"
    with pytest.raises(DataError, match="no recorded output"):
        asyncio.run(target(Example(input="other")))
    with pytest.raises(DataError, match="no recorded output to replay"):
        RecordedTarget.from_rows([(example, None)])
