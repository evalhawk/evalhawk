"""A cheap judge that escalates to a strong judge when unsure (a composite Judge).

``CascadeJudge`` is itself a :class:`~evalhawk.core.protocols.Judge`, so cascades nest
(cheap → medium → strong). Its ``judge_id`` includes both judges and the threshold, so a
new threshold is a new judge whose calibration is measured again.
"""

from evalhawk.core.ids import content_id
from evalhawk.core.models import Criterion, Example, Outcome, Trace, Verdict
from evalhawk.core.protocols import Judge


class CascadeJudge:
    """Accept the cheap verdict if ``P(PASS) >= threshold`` or ``<= 1 - threshold``.

    Otherwise (including when the cheap judge gives no probability, or UNKNOWN) the
    strong judge decides. Choose ``threshold`` on dev labels with
    ``evalhawk judges cascade``; the cost is the cheap call plus any escalations.
    """

    def __init__(self, cheap: Judge, strong: Judge, *, threshold: float) -> None:
        if not 0.5 <= threshold <= 1.0:
            raise ValueError(f"threshold must be in [0.5, 1], got {threshold}")
        self.cheap = cheap
        self.strong = strong
        self.threshold = float(threshold)
        self.judge_id = content_id(["cascade-v1", cheap.judge_id, strong.judge_id, self.threshold])

    async def judge(self, example: Example, trace: Trace, criterion: Criterion) -> Verdict:
        first = await self.cheap.judge(example, trace, criterion)
        p = first.probability
        confident = (
            first.outcome is not Outcome.UNKNOWN
            and p is not None
            and (p >= self.threshold or p <= 1 - self.threshold)
        )
        if confident:
            return first.model_copy(
                update={
                    "judge_id": self.judge_id,
                    "reasoning": f"[cheap judge, P(PASS)={p:.2f}] {first.reasoning or ''}".strip(),
                }
            )
        second = await self.strong.judge(example, trace, criterion)
        shown = "none" if p is None else f"{p:.2f}"
        return second.model_copy(
            update={
                "judge_id": self.judge_id,
                "cost_usd": first.cost_usd + second.cost_usd,
                "latency_ms": first.latency_ms + second.latency_ms,
                "reasoning": (
                    f"[escalated: cheap P(PASS)={shown}] {second.reasoning or ''}"
                ).strip(),
            }
        )
