"""Evaluate a model directly: the target *is* an OpenAI-compatible chat model."""

import asyncio
import json
import os
import time
from collections.abc import Mapping

from evalhawk.core.errors import CallError, ConfigError
from evalhawk.core.models import Example, TargetOutput
from evalhawk.transport.http import request_json


class OpenAICompatibleTarget:
    """Send each example's input to ``POST {base_url}/chat/completions`` and keep the reply."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        system_prompt: str | None = None,
        api_key_env: str | None = None,
        headers: Mapping[str, str] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: float = 120.0,
        verify: bool | str = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.api_key_env = api_key_env
        self.headers = dict(headers or {})
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.timeout = float(timeout)
        self.verify = verify

    def _headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self.api_key_env:
            key = os.environ.get(self.api_key_env)
            if not key:
                raise ConfigError(f"environment variable {self.api_key_env} is not set")
            headers["Authorization"] = f"Bearer {key}"
        return headers

    async def __call__(self, example: Example) -> TargetOutput:
        user = (
            example.input
            if isinstance(example.input, str)
            else json.dumps(example.input, ensure_ascii=False)
        )
        messages = [{"role": "user", "content": user}]
        if self.system_prompt:
            messages.insert(0, {"role": "system", "content": self.system_prompt})
        start = time.perf_counter()
        data = await asyncio.to_thread(
            request_json,
            "POST",
            f"{self.base_url}/chat/completions",
            {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
            headers=self._headers(),
            timeout=self.timeout,
            verify=self.verify,
        )
        latency = (time.perf_counter() - start) * 1000
        try:
            text = str(data["choices"][0]["message"]["content"] or "")  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise CallError(f"{self.base_url}: unexpected chat response shape: {exc}") from exc
        usage = data.get("usage") if isinstance(data, dict) else None
        return TargetOutput(
            output=text,
            usage=usage if isinstance(usage, dict) else {},
            latency_ms=latency,
        )
