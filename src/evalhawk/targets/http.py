"""Call the application under test over HTTP."""

import asyncio
import json
import re
import time
from collections.abc import Mapping
from typing import Any

from evalhawk.core.errors import CallError
from evalhawk.core.models import Example, TargetOutput
from evalhawk.transport import jsonpath
from evalhawk.transport.http import request_json

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}")


def _value(example: Example, name: str) -> Any:
    if name == "input":
        return example.input
    if name == "reference":
        return example.reference
    if name == "group_id":
        return example.group_id
    value: Any = example.input
    for part in name.removeprefix("input.").split("."):
        if not isinstance(value, dict) or part not in value:
            raise CallError(f"body template uses {{{{{name}}}}} but the example has no such field")
        value = value[part]
    return value


def fill(template: Any, example: Example) -> Any:
    """Substitute ``{{input}}``, ``{{reference}}`` and ``{{input.field}}`` placeholders.

    In a structured body, a string that is exactly one placeholder becomes the value
    itself (object, number...); placeholders inside longer strings become text.
    """
    if isinstance(template, str):
        whole = _PLACEHOLDER.fullmatch(template.strip())
        if whole:
            return _value(example, whole.group(1))
        return _PLACEHOLDER.sub(
            lambda m: v if isinstance(v := _value(example, m.group(1)), str) else json.dumps(v),
            template,
        )
    if isinstance(template, Mapping):
        return {key: fill(item, example) for key, item in template.items()}
    if isinstance(template, list):
        return [fill(item, example) for item in template]
    return template


class HttpTarget:
    """POST each example to your API and read the answer from the JSON response.

    Args:
        url: the endpoint.
        body: the JSON body, with placeholders, e.g. ``{"message": "{{input}}"}``.
        answer_path: JSONPath to the answer text, e.g. ``$.reply.text``.
        contexts_path: JSONPath to retrieved documents for RAG, e.g. ``$.sources[*].text``.
        headers: HTTP headers. ``${ENV}`` values are expanded when the config is loaded.
    """

    def __init__(
        self,
        *,
        url: str,
        body: Any = None,
        answer_path: str = "$.output",
        contexts_path: str | None = None,
        method: str = "POST",
        headers: Mapping[str, str] | None = None,
        timeout: float = 60.0,
        verify: bool | str = True,
    ) -> None:
        jsonpath.validate(answer_path)
        if contexts_path:
            jsonpath.validate(contexts_path)
        self.url = url
        self.body = body if body is not None else {"input": "{{input}}"}
        self.answer_path = answer_path
        self.contexts_path = contexts_path
        self.method = method.upper()
        self.headers = dict(headers or {})
        self.timeout = float(timeout)
        self.verify = verify

    async def __call__(self, example: Example) -> TargetOutput:
        start = time.perf_counter()
        data = await asyncio.to_thread(
            request_json,
            self.method,
            self.url,
            fill(self.body, example),
            headers=self.headers,
            timeout=self.timeout,
            verify=self.verify,
        )
        latency = (time.perf_counter() - start) * 1000
        answers = jsonpath.find(data, self.answer_path)
        if not answers or not isinstance(answers[0], str):
            raise CallError(
                f"{self.url}: no text answer at {self.answer_path}; check answer_path "
                f"against the response: {json.dumps(data)[:200]}"
            )
        contexts = None
        if self.contexts_path:
            contexts = tuple(str(item) for item in jsonpath.find(data, self.contexts_path))
        return TargetOutput(output=answers[0], contexts=contexts, latency_ms=latency)
