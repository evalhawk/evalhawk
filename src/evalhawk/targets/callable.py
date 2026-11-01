"""Call a Python function as the application under test."""

import asyncio
import inspect
import time
from collections.abc import Callable, Mapping
from typing import Any

from evalhawk.core.errors import DataError
from evalhawk.core.models import Example, TargetOutput


def to_output(result: Any, *, latency_ms: float = 0.0) -> TargetOutput:
    """Accept ``str``, :class:`TargetOutput`, or ``{"output": ..., "contexts": [...],
    "retrieved_ids": [...]}``."""
    if isinstance(result, TargetOutput):
        return result if result.latency_ms else result.model_copy(update={"latency_ms": latency_ms})
    if isinstance(result, str):
        return TargetOutput(output=result, latency_ms=latency_ms)
    if isinstance(result, Mapping) and "output" in result:
        data = {
            k: v for k, v in result.items() if k in {"output", "contexts", "retrieved_ids", "usage"}
        }
        for key in ("contexts", "retrieved_ids"):
            if data.get(key) is not None:
                data[key] = tuple(str(item) for item in data[key])
        return TargetOutput.model_validate({**data, "latency_ms": latency_ms})
    raise DataError(
        f"target returned {type(result).__name__}; return a str, a TargetOutput, or a dict "
        "with an 'output' key (and optional 'contexts')"
    )


class CallableTarget:
    """Wrap your app's function. It receives the example's ``input`` (or the whole
    :class:`Example` with ``pass_example=True``); sync functions run in a worker thread
    so they don't block other calls."""

    def __init__(self, fn: Callable[..., Any], *, pass_example: bool = False) -> None:
        self.fn = fn
        self.pass_example = pass_example

    async def __call__(self, example: Example) -> TargetOutput:
        argument = example if self.pass_example else example.input
        start = time.perf_counter()
        if inspect.iscoroutinefunction(self.fn):
            result = await self.fn(argument)
        else:
            result = await asyncio.to_thread(self.fn, argument)
            if inspect.isawaitable(result):
                result = await result
        return to_output(result, latency_ms=(time.perf_counter() - start) * 1000)
