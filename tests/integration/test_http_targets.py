"""HTTP and OpenAI-compatible targets against a local server (no internet)."""

import asyncio

import pytest

from evalhawk.core.errors import CallError
from evalhawk.core.models import Example
from evalhawk.targets.http import HttpTarget
from evalhawk.targets.openai_compat import OpenAICompatibleTarget
from evalhawk.testing.fake_llm import FakeLLMServer, chat_reply


def test_http_target_reads_answer_and_contexts(llm_server: FakeLLMServer) -> None:
    llm_server.respond = lambda payload: (
        200,
        {"reply": {"text": f"echo: {payload['message']}", "sources": [{"text": "doc 1"}]}},
    )
    target = HttpTarget(
        url=llm_server.url + "/chat",
        body={"message": "{{input}}", "session": "eval"},
        answer_path="$.reply.text",
        contexts_path="$.reply.sources[*].text",
        headers={"Authorization": "Bearer token"},
    )
    out = asyncio.run(target(Example(input="refund policy?")))
    assert out.output == "echo: refund policy?"
    assert out.contexts == ("doc 1",)
    assert llm_server.requests[0] == {"message": "refund policy?", "session": "eval"}
    assert llm_server.headers[0]["authorization"] == "Bearer token"


def test_http_target_explains_a_wrong_answer_path(llm_server: FakeLLMServer) -> None:
    llm_server.respond = lambda _p: (200, {"answer": "hi"})
    target = HttpTarget(url=llm_server.url, answer_path="$.reply.text")
    with pytest.raises(CallError, match=r"no text answer at \$\.reply\.text"):
        asyncio.run(target(Example(input="q")))


def test_openai_compatible_target(llm_server: FakeLLMServer) -> None:
    llm_server.respond = lambda _p: (200, chat_reply("Our refund window is 30 days."))
    target = OpenAICompatibleTarget(
        base_url=llm_server.url, model="support-bot", system_prompt="You are a support agent."
    )
    out = asyncio.run(target(Example(input="refund policy?")))
    assert out.output == "Our refund window is 30 days."
    assert out.usage["prompt_tokens"] == 100
    sent = llm_server.requests[0]
    assert sent["messages"][0] == {"role": "system", "content": "You are a support agent."}
    assert sent["messages"][1] == {"role": "user", "content": "refund policy?"}
