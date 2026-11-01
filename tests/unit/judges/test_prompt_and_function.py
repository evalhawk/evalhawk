import asyncio

import pytest

from evalhawk.core.models import Criterion, Example, Outcome, Trace
from evalhawk.judges.criteria import builtin_criterion
from evalhawk.judges.function import FunctionJudge
from evalhawk.judges.openai_compat import OpenAICompatibleJudge, pass_probability
from evalhawk.judges.prompt import Completion, PromptJudge, render_messages

EXAMPLE = Example(input="What's your refund policy?", reference="Refunds within 30 days.")
TRACE = Trace(
    example_id=EXAMPLE.id,
    run_id="run",
    output="Refunds within 30 days, back to your card.",
    contexts=("Refunds are available within 30 days.",),
)


def test_prompt_contains_everything_the_judge_needs() -> None:
    criterion = builtin_criterion("faithfulness").criterion()
    system, user = render_messages(EXAMPLE, TRACE, criterion)
    assert system["role"] == "system"
    text = user["content"]
    for expected in (
        criterion.question,
        "SUPPORTED by the context",  # the built-in guidance
        "What's your refund policy?",
        "Refunds within 30 days.",  # reference
        "[1] Refunds are available within 30 days.",  # numbered context
        "back to your card",  # the answer
        "VERDICT: PASS",  # reply instructions
    ):
        assert expected in text
    assert text.index("## Answer to evaluate") > text.index("## Retrieved context")


def test_custom_criterion_has_no_guidance_section_and_json_input_is_readable() -> None:
    example = Example(input={"ticket": "A-1", "text": "Where is my order?"})
    trace = Trace(example_id=example.id, run_id="run", output="It ships today.")
    _, user = render_messages(example, trace, Criterion(name="polite", question="Is it polite?"))
    assert "## How to judge" not in user["content"]
    assert '"ticket": "A-1"' in user["content"]


class EchoJudge(PromptJudge):
    adapter = "echo"

    def __init__(self, reply: str, **kwargs: object) -> None:
        super().__init__(model="echo-1", **kwargs)  # type: ignore[arg-type]
        self.reply = reply

    async def complete(self, messages: list[dict[str, str]]) -> Completion:
        return Completion(text=self.reply, probability=0.8, cost_usd=0.01, latency_ms=5)


def test_prompt_judge_builds_a_verdict() -> None:
    criterion = Criterion(name="c", question="Is it right?")
    verdict = asyncio.run(EchoJudge("Looks right.\nVERDICT: PASS").judge(EXAMPLE, TRACE, criterion))
    assert verdict.outcome is Outcome.PASS
    assert verdict.probability == 0.8
    assert verdict.reasoning == "Looks right."
    assert (verdict.cost_usd, verdict.latency_ms) == (0.01, 5)
    assert (verdict.trace_id, verdict.criterion_id) == (TRACE.id, criterion.id)


def test_unknown_verdicts_drop_the_probability() -> None:
    verdict = asyncio.run(
        EchoJudge("no idea").judge(EXAMPLE, TRACE, Criterion(name="c", question="Q?"))
    )
    assert verdict.outcome is Outcome.UNKNOWN
    assert verdict.probability is None


def test_judge_id_changes_with_behaviour_but_not_with_secrets() -> None:
    def judge(**kw: object) -> str:
        defaults: dict[str, object] = {"base_url": "http://localhost:11434/v1", "model": "qwen3:8b"}
        return OpenAICompatibleJudge(**{**defaults, **kw}).judge_id  # type: ignore[arg-type]

    base = judge()
    assert judge() == base
    assert judge(model="llama3.1:8b") != base
    assert judge(temperature=0.7) != base
    assert judge(mode="verdict_only") != base
    assert judge(guidance={"faithfulness": "be strict"}) != base
    # credentials and transport settings are not part of what the judge *is*
    assert judge(api_key_env="MY_KEY", headers={"X-Team": "a"}, verify=False, timeout=5) == base


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        ([{"token": "PASS", "logprob": -0.1}, {"token": "FAIL", "logprob": -2.4}], 0.909),
        ([{"token": "P", "logprob": -1.0}, {"token": "FA", "logprob": -1.0}], 0.5),
        ([{"token": " fail", "logprob": 0.0}], 0.0),
        ([{"token": "Yes", "logprob": 0.0}], None),
    ],
)
def test_pass_probability_from_logprobs(
    tokens: list[dict[str, object]], expected: float | None
) -> None:
    result = pass_probability(tokens)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected, abs=1e-3)


def test_function_judge_accepts_bools_outcomes_and_async() -> None:
    criterion = Criterion(name="c", question="Q?")

    async def is_short(example: Example, trace: Trace, criterion: Criterion) -> tuple[bool, float]:
        return len(trace.output) < 100, 0.7

    sync = FunctionJudge(lambda e, t, c: "fail", name="always-fail")
    async_judge = FunctionJudge(is_short, name="short")
    assert asyncio.run(sync.judge(EXAMPLE, TRACE, criterion)).outcome is Outcome.FAIL
    verdict = asyncio.run(async_judge.judge(EXAMPLE, TRACE, criterion))
    assert (verdict.outcome, verdict.probability) == (Outcome.PASS, 0.7)
    assert (
        FunctionJudge(lambda e, t, c: True, name="x", version="2").judge_id
        != FunctionJudge(lambda e, t, c: True, name="x").judge_id
    )
    with pytest.raises(ValueError, match="PASS/FAIL/UNKNOWN"):
        asyncio.run(
            FunctionJudge(lambda e, t, c: "maybe", name="bad").judge(EXAMPLE, TRACE, criterion)
        )
