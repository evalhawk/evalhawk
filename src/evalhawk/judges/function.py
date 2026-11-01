"""Wrap any Python function as a judge."""

import inspect
from collections.abc import Awaitable, Callable

from evalhawk.core.ids import content_id
from evalhawk.core.models import Criterion, Example, Outcome, Trace, Verdict

FunctionResult = bool | Outcome | str | tuple[bool | Outcome | str, float | None]
JudgeFunction = Callable[[Example, Trace, Criterion], FunctionResult | Awaitable[FunctionResult]]


def _outcome(value: bool | Outcome | str) -> Outcome:
    if isinstance(value, bool):
        return Outcome.PASS if value else Outcome.FAIL
    try:
        return Outcome(str(value).upper())
    except ValueError:
        raise ValueError(
            f"judge function returned {value!r}; return PASS/FAIL/UNKNOWN or a bool"
        ) from None


class FunctionJudge:
    """A judge backed by your own function (sync or async).

    The function receives ``(example, trace, criterion)`` and returns a bool, an
    :class:`Outcome` (or its name), or ``(outcome, probability)``. Its code is not hashed,
    so **bump ``version`` whenever you change the function**: that gives it a new
    ``judge_id`` and keeps old verdicts and calibration separate.
    """

    def __init__(self, fn: JudgeFunction, *, name: str, version: str = "1") -> None:
        self.fn = fn
        self.name = name
        self.version = version
        self.judge_id = content_id(["function-judge-v1", name, version])

    async def judge(self, example: Example, trace: Trace, criterion: Criterion) -> Verdict:
        result = self.fn(example, trace, criterion)
        if inspect.isawaitable(result):
            result = await result
        probability = None
        if isinstance(result, tuple):
            result, probability = result
        return Verdict(
            trace_id=trace.id,
            criterion_id=criterion.id,
            judge_id=self.judge_id,
            outcome=_outcome(result),
            probability=probability,
        )
