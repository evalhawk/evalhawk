import asyncio

import numpy as np

from evalhawk.core.models import Criterion, Example, Outcome, Run, TargetOutput, Trace
from evalhawk.core.protocols import Judge, Target
from evalhawk.testing.fakes import FakeJudge, FakeTarget


def test_fakes_satisfy_protocols_without_inheritance() -> None:
    example = Example(input="question")
    target = FakeTarget({example.id: TargetOutput(output="answer")})
    assert isinstance(target, Target)
    assert asyncio.run(target(example)).output == "answer"
    assert isinstance(FakeJudge(1, 1, truth={}, rng=np.random.default_rng(1)), Judge)


def test_fake_judge_known_rates() -> None:
    run = Run(target_version="fake")
    criterion = Criterion(name="correct", question="Correct?")
    traces = [
        Trace(example_id=str(index), run_id=run.id, output="answer") for index in range(10_000)
    ]
    truth = {
        trace.id: Outcome.PASS if index < 5000 else Outcome.FAIL
        for index, trace in enumerate(traces)
    }
    judge = FakeJudge(0.9, 0.7, truth=truth, rng=np.random.default_rng(42))

    async def measure() -> list[Outcome]:
        return [(await judge.judge(trace, criterion)).outcome for trace in traces]

    outcomes = asyncio.run(measure())
    assert abs(sum(item == Outcome.PASS for item in outcomes[:5000]) / 5000 - 0.9) < 0.01
    assert abs(sum(item == Outcome.FAIL for item in outcomes[5000:]) / 5000 - 0.7) < 0.01
