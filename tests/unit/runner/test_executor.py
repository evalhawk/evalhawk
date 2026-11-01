"""The runner's promises: resume, never pay twice, retries, limits and budget."""

import asyncio
from collections.abc import Sequence

import pytest

from evalhawk.core.errors import CallError
from evalhawk.core.models import Criterion, Example, Outcome, Run, TargetOutput, Trace, Verdict
from evalhawk.runner.executor import JudgeSpec, RunnerSettings, execute
from evalhawk.testing.fakes import InMemoryStore

FAST = RunnerSettings(max_concurrency=4, retries=2, base_delay=0.0, timeout=5.0)
CRITERIA = [
    Criterion(name="correct", question="Correct?"),
    Criterion(name="polite", question="Polite?"),
]


class CountingTarget:
    def __init__(
        self, answer: str = "same answer", contexts: tuple[str, ...] | None = None
    ) -> None:
        self.calls = 0
        self.answer = answer
        self.contexts = contexts

    async def __call__(self, example: Example) -> TargetOutput:
        self.calls += 1
        return TargetOutput(output=f"{self.answer}", contexts=self.contexts)


class CountingJudge:
    def __init__(
        self,
        judge_id: str = "judge-1",
        *,
        failures: Sequence[Exception] = (),
        cost: float = 0.0,
        delay: float = 0.0,
    ) -> None:
        self.judge_id = judge_id
        self.calls = 0
        self.failures = list(failures)
        self.cost = cost
        self.delay = delay
        self.active = 0
        self.max_active = 0

    async def judge(self, example: Example, trace: Trace, criterion: Criterion) -> Verdict:
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay)
            if self.failures:
                raise self.failures.pop(0)
            return Verdict(
                trace_id=trace.id,
                criterion_id=criterion.id,
                judge_id=self.judge_id,
                outcome=Outcome.PASS,
                cost_usd=self.cost,
            )
        finally:
            self.active -= 1


def _examples(n: int) -> list[Example]:
    return [Example(input=f"question {i}") for i in range(n)]


def _run(
    store: InMemoryStore,
    run: Run,
    examples: list[Example],
    target: CountingTarget,
    judge: CountingJudge,
    *,
    repeats: int = 1,
    settings: RunnerSettings = FAST,
    require_contexts: bool = False,
):
    store.add_examples(examples)
    specs = [JudgeSpec(criterion, judge) for criterion in CRITERIA]
    return asyncio.run(
        execute(
            store,
            run,
            examples,
            target,
            specs,
            repeats=repeats,
            settings=settings,
            require_contexts=require_contexts,
        )
    )


def test_first_run_calls_everything_once() -> None:
    store, target, judge = InMemoryStore(), CountingTarget(answer="a"), CountingJudge()
    summary = _run(store, Run(target_version="v1"), _examples(5), target, judge)
    assert target.calls == 5
    assert summary.traces_new == 5
    # all 5 answers are identical text, but the questions differ, so 10 real judgments
    assert judge.calls == 10
    assert summary.verdicts_new == 10
    assert len(store.verdicts) == 10
    assert summary.failures == ()


def test_rerunning_the_same_run_resumes_for_free() -> None:
    store, target, judge = InMemoryStore(), CountingTarget(), CountingJudge()
    run, examples = Run(target_version="v1"), _examples(3)
    _run(store, run, examples, target, judge)
    target.calls = judge.calls = 0
    summary = _run(store, run, examples, target, judge)
    assert (target.calls, judge.calls) == (0, 0)
    assert summary.traces_reused == 3
    assert summary.verdicts_existing == 6


def test_identical_answers_in_a_new_version_reuse_cached_judgments() -> None:
    store, judge = InMemoryStore(), CountingJudge()
    examples = _examples(3)
    _run(store, Run(target_version="v1"), examples, CountingTarget("same"), judge)
    judge.calls = 0
    summary = _run(store, Run(target_version="v2"), examples, CountingTarget("same"), judge)
    assert judge.calls == 0  # the judge would see exactly the same thing
    assert summary.verdicts_cached == 6
    assert len(store.verdicts) == 12  # every trace still has its own verdicts
    changed = _run(store, Run(target_version="v3"), examples, CountingTarget("new"), judge)
    assert changed.verdicts_new == 6  # a different answer is judged again


def test_repeats_create_separate_traces_but_one_judgment_per_identical_answer() -> None:
    store, target, judge = InMemoryStore(), CountingTarget("deterministic"), CountingJudge()
    summary = _run(store, Run(target_version="v1"), _examples(2), target, judge, repeats=3)
    assert target.calls == 6
    assert len(store.traces) == 6
    assert {t.repeat_index for t in store.traces.values()} == {0, 1, 2}
    assert judge.calls == 4  # 2 questions x 2 criteria; repeats 1 and 2 hit the cache
    assert len(store.verdicts) == 12
    assert summary.verdicts_cached == 8


def test_retryable_failures_are_retried_then_succeed() -> None:
    store, target = InMemoryStore(), CountingTarget()
    judge = CountingJudge(
        failures=[CallError("429", retryable=True), CallError("503", retryable=True)]
    )
    summary = _run(store, Run(target_version="v1"), _examples(1), target, judge)
    assert summary.failures == ()
    assert summary.verdicts_new == 2
    assert judge.calls == 4  # 2 failures + 2 successes


def test_non_retryable_failures_are_recorded_and_the_rest_continues() -> None:
    store, target = InMemoryStore(), CountingTarget()
    judge = CountingJudge(failures=[CallError("401 bad key", retryable=False)])
    summary = _run(store, Run(target_version="v1"), _examples(2), target, judge)
    assert len(summary.failures) == 1
    failure = summary.failures[0]
    assert failure.stage == "judge"
    assert "401" in failure.error
    assert failure.attempts == 1
    assert summary.verdicts_new == 3


def test_timeouts_become_failures_after_retries() -> None:
    store, target = InMemoryStore(), CountingTarget()
    judge = CountingJudge(delay=0.5)
    settings = RunnerSettings(max_concurrency=2, retries=1, base_delay=0.0, timeout=0.05)
    summary = _run(store, Run(target_version="v1"), _examples(1), target, judge, settings=settings)
    assert len(summary.failures) == 2
    assert all("timed out" in f.error and f.attempts == 2 for f in summary.failures)


def test_concurrency_limit_is_respected() -> None:
    store, target = InMemoryStore(), CountingTarget(answer="x")
    judge = CountingJudge(delay=0.02)
    settings = RunnerSettings(max_concurrency=3, retries=0, base_delay=0.0)
    _run(store, Run(target_version="v1"), _examples(12), target, judge, settings=settings)
    assert judge.max_active <= 3


def test_budget_stops_new_paid_calls() -> None:
    store, target = InMemoryStore(), CountingTarget()
    judge = CountingJudge(cost=1.0)
    settings = RunnerSettings(max_concurrency=1, retries=0, base_delay=0.0, max_cost_usd=2.5)
    summary = _run(store, Run(target_version="v1"), _examples(5), target, judge, settings=settings)
    assert judge.calls == 3  # calls start only while spend < limit; one call may be in flight
    assert summary.budget_stopped
    assert summary.cost_usd == pytest.approx(3.0)
    assert summary.skipped_for_budget == 7


def test_rag_runs_require_contexts_from_the_target() -> None:
    store, judge = InMemoryStore(), CountingJudge()
    summary = _run(
        store,
        Run(target_version="v1"),
        _examples(1),
        CountingTarget(),
        judge,
        require_contexts=True,
    )
    assert judge.calls == 0
    assert len(summary.failures) == 1
    assert "contexts" in summary.failures[0].error
    ok = _run(
        store,
        Run(target_version="v2"),
        _examples(1),
        CountingTarget(contexts=("doc",)),
        judge,
        require_contexts=True,
    )
    assert ok.failures == ()
