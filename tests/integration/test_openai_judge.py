"""The OpenAI-compatible judge against a real local HTTP server (no internet)."""

import asyncio

import pytest

from evalhawk.core.errors import CallError, ConfigError
from evalhawk.core.models import Criterion, Example, Outcome, Trace
from evalhawk.judges.openai_compat import OpenAICompatibleJudge
from evalhawk.testing.fake_llm import FakeLLMServer, chat_reply

EXAMPLE = Example(input="2+2?", reference="4")
TRACE = Trace(example_id=EXAMPLE.id, run_id="run", output="4")
CRITERION = Criterion(
    name="correctness", question="Is the answer consistent with the reference answer?"
)


def test_judge_round_trip_with_cost(llm_server: FakeLLMServer) -> None:
    llm_server.respond = lambda _p: (
        200,
        chat_reply("Matches.\nVERDICT: PASS", prompt_tokens=1000, completion_tokens=100),
    )
    judge = OpenAICompatibleJudge(
        base_url=llm_server.url, model="qwen3:8b", price_per_1k_input=0.5, price_per_1k_output=1.5
    )
    verdict = asyncio.run(judge.judge(EXAMPLE, TRACE, CRITERION))
    assert verdict.outcome is Outcome.PASS
    assert verdict.cost_usd == pytest.approx(0.5 + 0.15)
    sent = llm_server.requests[0]
    assert sent["model"] == "qwen3:8b"
    assert sent["temperature"] == 0.0
    assert "logprobs" not in sent
    assert "Is the answer consistent" in sent["messages"][1]["content"]


def test_verdict_only_mode_reads_probability(llm_server: FakeLLMServer) -> None:
    llm_server.respond = lambda _p: (
        200,
        chat_reply(
            "FAIL",
            top_logprobs=[{"token": "FAIL", "logprob": -0.2}, {"token": "PASS", "logprob": -1.8}],
        ),
    )
    judge = OpenAICompatibleJudge(base_url=llm_server.url, model="m", mode="verdict_only")
    verdict = asyncio.run(judge.judge(EXAMPLE, TRACE, CRITERION))
    assert verdict.outcome is Outcome.FAIL
    assert verdict.probability == pytest.approx(0.168, abs=1e-3)
    assert llm_server.requests[0]["logprobs"] is True


def test_api_key_comes_from_the_environment_only(
    llm_server: FakeLLMServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    judge = OpenAICompatibleJudge(
        base_url=llm_server.url,
        model="m",
        api_key_env="EVALHAWK_TEST_KEY",
        headers={"X-Team": "qa"},
    )
    monkeypatch.delenv("EVALHAWK_TEST_KEY", raising=False)
    with pytest.raises(ConfigError, match="EVALHAWK_TEST_KEY is not set"):
        asyncio.run(judge.judge(EXAMPLE, TRACE, CRITERION))
    monkeypatch.setenv("EVALHAWK_TEST_KEY", "sk-secret")
    asyncio.run(judge.judge(EXAMPLE, TRACE, CRITERION))
    assert llm_server.headers[-1]["authorization"] == "Bearer sk-secret"
    assert llm_server.headers[-1]["x-team"] == "qa"
    assert "sk-secret" not in judge.judge_id


@pytest.mark.parametrize(
    ("status", "retryable"), [(429, True), (503, True), (400, False), (401, False)]
)
def test_http_errors_say_whether_to_retry(
    llm_server: FakeLLMServer, status: int, retryable: bool
) -> None:
    llm_server.respond = lambda _p: (status, {"error": "nope"})
    judge = OpenAICompatibleJudge(base_url=llm_server.url, model="m")
    with pytest.raises(CallError) as caught:
        asyncio.run(judge.judge(EXAMPLE, TRACE, CRITERION))
    assert caught.value.retryable is retryable
    assert str(status) in str(caught.value)


def test_unreachable_server_is_retryable() -> None:
    judge = OpenAICompatibleJudge(base_url="http://127.0.0.1:9/v1", model="m", timeout=2)
    with pytest.raises(CallError) as caught:
        asyncio.run(judge.judge(EXAMPLE, TRACE, CRITERION))
    assert caught.value.retryable


def test_malformed_response_is_a_clear_error(llm_server: FakeLLMServer) -> None:
    llm_server.respond = lambda _p: (200, {"unexpected": True})
    judge = OpenAICompatibleJudge(base_url=llm_server.url, model="m")
    with pytest.raises(CallError, match="unexpected chat response shape"):
        asyncio.run(judge.judge(EXAMPLE, TRACE, CRITERION))


def test_reasoning_effort_is_sent_and_only_then_changes_the_judge_id(
    llm_server: FakeLLMServer,
) -> None:
    llm_server.respond = lambda _p: (200, chat_reply("VERDICT: PASS"))
    plain = OpenAICompatibleJudge(base_url=llm_server.url, model="m")
    quiet = OpenAICompatibleJudge(base_url=llm_server.url, model="m", reasoning_effort="none")
    asyncio.run(quiet.judge(EXAMPLE, TRACE, CRITERION))
    assert llm_server.requests[0]["reasoning_effort"] == "none"
    asyncio.run(plain.judge(EXAMPLE, TRACE, CRITERION))
    assert "reasoning_effort" not in llm_server.requests[1]
    assert plain.judge_id != quiet.judge_id
    assert plain.judge_id == OpenAICompatibleJudge(base_url=llm_server.url, model="m").judge_id
    with pytest.raises(ValueError, match="reasoning_effort"):
        OpenAICompatibleJudge(base_url=llm_server.url, model="m", reasoning_effort="very high")


def test_a_thinking_model_that_runs_out_of_tokens_gets_a_clear_error(
    llm_server: FakeLLMServer,
) -> None:
    body = chat_reply("")
    body["choices"][0]["finish_reason"] = "length"
    body["choices"][0]["message"]["reasoning"] = "Thinking Process: 1. Analyze..."
    llm_server.respond = lambda _p: (200, body)
    judge = OpenAICompatibleJudge(base_url=llm_server.url, model="qwen3.5:4b")
    with pytest.raises(
        CallError, match='spent all of it thinking.*reasoning_effort = "none"'
    ) as err:
        asyncio.run(judge.judge(EXAMPLE, TRACE, CRITERION))
    assert not err.value.retryable
