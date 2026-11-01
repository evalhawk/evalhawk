"""Cascades: routing, config wiring, and threshold tuning on dev labels."""

import asyncio
from pathlib import Path

import pytest

from evalhawk.config import Config, JudgeConfig
from evalhawk.core.errors import ConfigError
from evalhawk.core.models import Criterion, Example, Label, Outcome, TargetOutput, Trace, Verdict
from evalhawk.core.splits import SplitSet
from evalhawk.judges.cascade import CascadeJudge
from evalhawk.runner.executor import JudgeSpec
from evalhawk.services.cascade import analyse_cascade
from evalhawk.services.evaluate import find_or_create_run, run_evaluation, run_snapshot
from evalhawk.storage.sqlite import SQLiteStore
from evalhawk.testing.fakes import FakeTarget
from evalhawk.wiring import build_judge

CRITERION = Criterion(name="faithful", question="Is every claim supported?")
EXAMPLE = Example(input="q")
TRACE = Trace(example_id=EXAMPLE.id, run_id="run", output="answer")


class Fixed:
    def __init__(
        self, judge_id: str, outcome: Outcome, probability: float | None, cost: float
    ) -> None:
        self.judge_id = judge_id
        self.outcome, self.probability, self.cost = outcome, probability, cost
        self.calls = 0

    async def judge(self, example: Example, trace: Trace, criterion: Criterion) -> Verdict:
        self.calls += 1
        return Verdict(
            trace_id=trace.id,
            criterion_id=criterion.id,
            judge_id=self.judge_id,
            outcome=self.outcome,
            probability=self.probability,
            cost_usd=self.cost,
        )


@pytest.mark.parametrize(
    ("probability", "escalates"), [(0.95, False), (0.05, False), (0.7, True), (None, True)]
)
def test_cascade_routing(probability: float | None, escalates: bool) -> None:
    cheap = Fixed(
        "cheap", Outcome.PASS if (probability or 0) >= 0.5 else Outcome.FAIL, probability, 0.001
    )
    strong = Fixed("strong", Outcome.FAIL, None, 0.05)
    cascade = CascadeJudge(cheap, strong, threshold=0.9)
    verdict = asyncio.run(cascade.judge(EXAMPLE, TRACE, CRITERION))
    assert strong.calls == int(escalates)
    assert verdict.judge_id == cascade.judge_id
    if escalates:
        assert verdict.outcome is Outcome.FAIL
        assert verdict.cost_usd == pytest.approx(0.051)  # both calls are paid
        assert verdict.reasoning is not None
        assert verdict.reasoning.startswith("[escalated")
    else:
        assert verdict.cost_usd == pytest.approx(0.001)


def test_cascade_identity_depends_on_parts_and_threshold() -> None:
    a, b = Fixed("a", Outcome.PASS, 0.9, 0), Fixed("b", Outcome.PASS, None, 0)
    assert CascadeJudge(a, b, threshold=0.9).judge_id != CascadeJudge(a, b, threshold=0.8).judge_id
    assert CascadeJudge(a, b, threshold=0.9).judge_id != CascadeJudge(b, a, threshold=0.9).judge_id
    with pytest.raises(ValueError, match="threshold"):
        CascadeJudge(a, b, threshold=0.3)


def test_cascade_from_config_and_cycles_are_refused(tmp_path: Path) -> None:
    judges = {
        "small": JudgeConfig.model_validate(
            {"type": "openai_compatible", "base_url": "http://x/v1", "model": "s"}
        ),
        "large": JudgeConfig.model_validate(
            {"type": "openai_compatible", "base_url": "http://x/v1", "model": "l"}
        ),
        "combo": JudgeConfig.model_validate(
            {"type": "cascade", "cheap": "small", "strong": "large", "threshold": 0.85}
        ),
        "loop": JudgeConfig.model_validate({"type": "cascade", "cheap": "loop", "strong": "large"}),
        "broken": JudgeConfig.model_validate(
            {"type": "cascade", "cheap": "nope", "strong": "large"}
        ),
    }
    combo = build_judge("combo", judges["combo"], base_dir=tmp_path, others=judges)
    assert isinstance(combo, CascadeJudge)
    assert combo.threshold == 0.85
    with pytest.raises(ConfigError, match="cycle"):
        build_judge("loop", judges["loop"], base_dir=tmp_path, others=judges)
    with pytest.raises(ConfigError, match="not a defined judge"):
        build_judge("broken", judges["broken"], base_dir=tmp_path, others=judges)
    assert Config  # imported for type completeness


class Cheap:
    """Confident and right on easy items; unsure (and often wrong) on hard ones."""

    judge_id = "cheap-judge"

    async def judge(self, example: Example, trace: Trace, criterion: Criterion) -> Verdict:
        good, hard = "good" in trace.output, "hard" in trace.output
        if hard:
            outcome, p = (Outcome.FAIL, 0.4) if good else (Outcome.PASS, 0.6)
        else:
            outcome, p = (Outcome.PASS, 0.97) if good else (Outcome.FAIL, 0.03)
        return Verdict(
            trace_id=trace.id,
            criterion_id=criterion.id,
            judge_id=self.judge_id,
            outcome=outcome,
            probability=p,
        )


class Strong:
    judge_id = "strong-judge"

    async def judge(self, example: Example, trace: Trace, criterion: Criterion) -> Verdict:
        outcome = Outcome.PASS if "good" in trace.output else Outcome.FAIL
        return Verdict(
            trace_id=trace.id, criterion_id=criterion.id, judge_id=self.judge_id, outcome=outcome
        )


def test_tuning_finds_a_threshold_that_escalates_only_hard_items(tmp_path: Path) -> None:
    examples = [Example(input=f"case {i}") for i in range(120)]
    outputs = {
        e.id: TargetOutput(
            output=("good" if i % 2 else "bad") + (" hard" if i % 5 == 0 else " easy")
        )
        for i, e in enumerate(examples)
    }
    splits = SplitSet(salt="cascade-test")
    specs = [JudgeSpec(CRITERION, Cheap()), JudgeSpec(CRITERION, Strong())]
    snapshot = run_snapshot(
        evaluation="e",
        specs=specs,
        judge_names=["small", "large"],
        splits=splits,
        repeats=1,
        kind="single_turn",
        target={"type": "recorded"},
    )
    store = SQLiteStore(tmp_path / "c.db")
    try:
        run, _ = find_or_create_run(store, target_version="v1", snapshot=snapshot)
        asyncio.run(
            run_evaluation(
                store,
                run=run,
                examples=examples,
                target=FakeTarget(outputs),
                specs=specs,
                splits=splits,
            )
        )
        for example in examples:  # humans agree with the truth ("good" = PASS)
            trace = store.get_trace_slot(run.id, example.id, 0)
            assert trace is not None
            store.add_label(
                Label(
                    trace_id=trace.id,
                    criterion_id=CRITERION.id,
                    annotator="h",
                    outcome=Outcome.PASS if "good" in trace.output else Outcome.FAIL,
                )
            )
        result = analyse_cascade(
            store, run, criterion="faithful", cheap="small", strong="large", target_accuracy=0.99
        )
    finally:
        store.close()
    curve = result.curve
    assert curve.strong_accuracy.point == 1.0
    assert curve.cheap_accuracy.point < 0.9  # the cheap judge alone gets hard items wrong
    assert curve.chosen is not None
    assert curve.chosen.accuracy.point == 1.0
    assert 0.7 < curve.chosen.coverage < 0.9  # only the ~20% hard items are escalated
    conditional = result.errors.strong_wrong_given_cheap_wrong
    assert conditional is not None
    assert conditional.point == 0.0  # the strong judge is right exactly where the cheap one fails
    assert result.errors.lift is None  # undefined: the strong judge is never wrong at all
