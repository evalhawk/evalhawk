"""A judge for any OpenAI-compatible chat API: Ollama, OpenAI, Groq, OpenRouter, vLLM...

Standard library HTTP only (no ``openai`` package). API keys are read from an environment
variable named in config and are never stored, logged or hashed.
"""

import asyncio
import math
import os
import time
from collections.abc import Mapping, Sequence
from typing import ClassVar

from evalhawk.core.errors import CallError, ConfigError
from evalhawk.judges.prompt import Completion, Mode, PromptJudge
from evalhawk.transport.http import request_json


def pass_probability(top_logprobs: Sequence[Mapping[str, object]]) -> float | None:
    """P(PASS) from the first token's alternatives, normalised over PASS and FAIL.

    A word may be split into several tokens, so a token counts for PASS if it is a
    non-empty prefix of "PASS" starting with "P" (likewise for FAIL). Returns None when
    neither appears, so calibration metrics skip this judge instead of guessing.
    """
    mass = {"PASS": 0.0, "FAIL": 0.0}
    for item in top_logprobs:
        token = str(item.get("token", "")).strip().upper()
        logprob = item.get("logprob")
        if not token or not isinstance(logprob, int | float):
            continue
        for word in mass:
            if word.startswith(token) and token[0] == word[0]:
                mass[word] += math.exp(float(logprob))
    total = mass["PASS"] + mass["FAIL"]
    return mass["PASS"] / total if total > 0 else None


class OpenAICompatibleJudge(PromptJudge):
    """Judge through ``POST {base_url}/chat/completions``.

    Args:
        base_url: e.g. ``http://localhost:11434/v1`` (Ollama) or ``https://api.openai.com/v1``.
        model: the model name at that endpoint.
        api_key_env: name of the environment variable holding the API key (optional for
            local servers).
        headers: extra HTTP headers (e.g. for a corporate gateway).
        verify: ``True``, ``False`` or a path to a CA bundle.
        mode: ``reason_then_verdict`` (more accurate) or ``verdict_only`` (gives P(PASS)
            from logprobs when the provider supports them).
        price_per_1k_input, price_per_1k_output: USD prices, for budget tracking.
    """

    adapter: ClassVar[str] = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str | None = None,
        headers: Mapping[str, str] | None = None,
        verify: bool | str = True,
        timeout: float = 60.0,
        temperature: float = 0.0,
        max_tokens: int = 512,
        mode: Mode = "reason_then_verdict",
        price_per_1k_input: float = 0.0,
        price_per_1k_output: float = 0.0,
        guidance: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            model=model,
            mode=mode,
            params={
                "base_url": base_url.rstrip("/"),
                "temperature": float(temperature),
                "max_tokens": int(max_tokens),
            },
            guidance=guidance,
        )
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.headers = dict(headers or {})
        self.verify = verify
        self.timeout = float(timeout)
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.prices = (float(price_per_1k_input), float(price_per_1k_output))

    def _headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self.api_key_env:
            key = os.environ.get(self.api_key_env)
            if not key:
                raise ConfigError(
                    f"environment variable {self.api_key_env} is not set; export your API "
                    "key there (keys are never read from the config file)"
                )
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _payload(self, messages: list[dict[str, str]]) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.mode == "verdict_only":
            payload.update(logprobs=True, top_logprobs=5, max_tokens=min(self.max_tokens, 5))
        return payload

    async def complete(self, messages: list[dict[str, str]]) -> Completion:
        start = time.perf_counter()
        data = await asyncio.to_thread(
            request_json,
            "POST",
            f"{self.base_url}/chat/completions",
            self._payload(messages),
            headers=self._headers(),
            timeout=self.timeout,
            verify=self.verify,
        )
        latency = (time.perf_counter() - start) * 1000
        try:
            choice = data["choices"][0]  # type: ignore[index]
            text = str(choice["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise CallError(f"{self.base_url}: unexpected chat response shape: {exc}") from exc
        probability = None
        logprobs = choice.get("logprobs") if isinstance(choice, dict) else None
        if self.mode == "verdict_only" and isinstance(logprobs, dict):
            content = logprobs.get("content")
            if isinstance(content, list) and content and isinstance(content[0], dict):
                probability = pass_probability(content[0].get("top_logprobs") or [])
        usage = data.get("usage") if isinstance(data, dict) else None
        cost = 0.0
        if isinstance(usage, dict):
            cost = (
                float(usage.get("prompt_tokens", 0)) * self.prices[0]
                + float(usage.get("completion_tokens", 0)) * self.prices[1]
            ) / 1000
        return Completion(text=text, probability=probability, cost_usd=cost, latency_ms=latency)
