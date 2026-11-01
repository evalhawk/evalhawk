"""Run the application and its judges over a dataset: resumable, cached, bounded.

For each example (and repeat) the runner reuses the run's existing trace or calls the
target; then, for each (criterion, judge), it reuses an existing verdict, reuses a cached
judgment for identical content (the *judgment key*), or calls the judge. External calls
share one concurrency limit, are retried with exponential backoff and jitter when the
failure is temporary, are bounded by a timeout, and stop being scheduled once the budget
is spent. Failures are recorded, never silently dropped.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from evalhawk.core.errors import CallError, DataError
from evalhawk.core.models import Criterion, Example, Run, Trace, Verdict, judgment_key
from evalhawk.core.protocols import Judge, Store, Target

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class JudgeSpec:
    """Which judge decides which criterion."""

    criterion: Criterion
    judge: Judge


@dataclass(frozen=True, slots=True)
class RunnerSettings:
    """Concurrency, retry, timeout and budget settings (``[runner]`` in evalhawk.toml)."""

    max_concurrency: int = 8
    retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    timeout: float = 120.0
    max_cost_usd: float | None = None
    seed: int = 0

    def __post_init__(self) -> None:
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if self.retries < 0 or self.timeout <= 0:
            raise ValueError("retries must be >= 0 and timeout > 0")


@dataclass(frozen=True, slots=True)
class Failure:
    """One call that failed after its retries."""

    stage: str  # "target" or "judge"
    example_id: str
    repeat_index: int
    criterion: str | None
    error: str
    attempts: int


@dataclass(frozen=True, slots=True)
class RunSummary:
    """What the runner did, for the CLI and the run log."""

    traces_new: int
    traces_reused: int
    verdicts_new: int
    verdicts_cached: int
    verdicts_existing: int
    cost_usd: float
    budget_stopped: bool
    skipped_for_budget: int
    failures: tuple[Failure, ...]


@dataclass
class _State:
    settings: RunnerSettings
    semaphore: asyncio.Semaphore
    rng: random.Random
    counts: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(
            (
                "traces_new",
                "traces_reused",
                "verdicts_new",
                "verdicts_cached",
                "verdicts_existing",
                "skipped_for_budget",
            ),
            0,
        )
    )
    cost_usd: float = 0.0
    failures: list[Failure] = field(default_factory=list)
    inflight: dict[str, asyncio.Task[Verdict | None]] = field(default_factory=dict)

    @property
    def budget_exhausted(self) -> bool:
        limit = self.settings.max_cost_usd
        return limit is not None and self.cost_usd >= limit


class _BudgetSpentError(Exception):
    """Raised instead of starting a paid call once the budget is reached."""


class _GaveUpError(Exception):
    def __init__(self, error: str, attempts: int) -> None:
        super().__init__(error)
        self.error = error
        self.attempts = attempts


async def _call(state: _State, make: Callable[[], Awaitable[T]], *, paid: bool = False) -> T:
    """One external call: limited concurrency, timeout, and retries for temporary errors."""
    settings = state.settings
    attempt = 0
    while True:
        attempt += 1
        try:
            async with state.semaphore:
                # Check the budget only once a call slot is free, so queued calls can't
                # all pass the check while the spend is still zero.
                if paid and state.budget_exhausted:
                    raise _BudgetSpentError
                return await asyncio.wait_for(make(), timeout=settings.timeout)
        except TimeoutError:
            error, retryable = f"timed out after {settings.timeout:g}s", True
        except CallError as exc:
            error, retryable = str(exc), exc.retryable
        if not retryable or attempt > settings.retries:
            raise _GaveUpError(error, attempt)
        delay = min(settings.max_delay, settings.base_delay * 2 ** (attempt - 1))
        await asyncio.sleep(delay * (0.5 + state.rng.random() / 2))  # jitter


async def _judgment(
    state: _State, store: Store, example: Example, trace: Trace, spec: JudgeSpec
) -> Verdict | None:
    """A paid judge call (or None if the budget stopped it); deduplicated while in flight."""
    try:
        verdict = await _call(
            state, lambda: spec.judge.judge(example, trace, spec.criterion), paid=True
        )
    except _BudgetSpentError:
        state.counts["skipped_for_budget"] += 1
        return None
    except _GaveUpError as gave_up:
        state.failures.append(
            Failure(
                "judge",
                example.id,
                trace.repeat_index,
                spec.criterion.name,
                gave_up.error,
                gave_up.attempts,
            )
        )
        return None
    state.cost_usd += verdict.cost_usd
    return verdict


async def _judge_one(
    state: _State, store: Store, example: Example, trace: Trace, spec: JudgeSpec
) -> None:
    criterion, judge_id = spec.criterion, spec.judge.judge_id
    if store.get_verdict(trace.id, criterion.id, judge_id) is not None:
        state.counts["verdicts_existing"] += 1
        return
    key = judgment_key(example, trace, criterion, judge_id)
    cached = store.get_judgment(key)
    if cached is None and key in state.inflight:
        cached = await state.inflight[key]  # same content is being judged right now
        if cached is None:
            return  # the first request failed or hit the budget, and recorded why
    if cached is not None:
        store.put_verdict(
            Verdict(
                trace_id=trace.id,
                criterion_id=criterion.id,
                judge_id=judge_id,
                outcome=cached.outcome,
                probability=cached.probability,
                reasoning=cached.reasoning,
            )
        )
        state.counts["verdicts_cached"] += 1
        return
    task = asyncio.ensure_future(_judgment(state, store, example, trace, spec))
    state.inflight[key] = task
    try:
        verdict = await task
    finally:
        state.inflight.pop(key, None)
    if verdict is None:
        return
    store.put_verdict(verdict)
    store.put_judgment(key, verdict)
    state.counts["verdicts_new"] += 1


async def _one_case(
    state: _State,
    store: Store,
    run: Run,
    example: Example,
    repeat: int,
    target: Target,
    specs: Sequence[JudgeSpec],
    require_contexts: bool,
) -> None:
    trace = store.get_trace_slot(run.id, example.id, repeat)
    if trace is not None:
        state.counts["traces_reused"] += 1
    else:
        try:
            output = await _call(state, lambda: target(example))
        except _GaveUpError as gave_up:
            state.failures.append(
                Failure("target", example.id, repeat, None, gave_up.error, gave_up.attempts)
            )
            return
        if require_contexts and output.contexts is None:
            state.failures.append(
                Failure(
                    "target",
                    example.id,
                    repeat,
                    None,
                    str(
                        DataError(
                            "rag evaluation: the target returned no contexts; "
                            "set contexts_path or return 'contexts'"
                        )
                    ),
                    1,
                )
            )
            return
        trace = Trace(
            **output.model_dump(), example_id=example.id, run_id=run.id, repeat_index=repeat
        )
        store.add_traces(run, [trace])
        state.counts["traces_new"] += 1
    await asyncio.gather(*(_judge_one(state, store, example, trace, spec) for spec in specs))


async def execute(
    store: Store,
    run: Run,
    examples: Sequence[Example],
    target: Target,
    specs: Sequence[JudgeSpec],
    *,
    repeats: int = 1,
    settings: RunnerSettings | None = None,
    require_contexts: bool = False,
) -> RunSummary:
    """Run ``target`` on every example ``repeats`` times and judge every trace.

    Examples must already be in the store (the evaluate service adds them and locks their
    splits first). Re-running the same ``run`` resumes: existing traces and verdicts are
    reused, and only the gaps are filled.
    """
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    settings = settings or RunnerSettings()
    state = _State(
        settings, asyncio.Semaphore(settings.max_concurrency), random.Random(settings.seed)
    )
    store.add_run(run)
    for spec in specs:
        store.add_criterion(spec.criterion)
    await asyncio.gather(
        *(
            _one_case(state, store, run, example, repeat, target, specs, require_contexts)
            for example in examples
            for repeat in range(repeats)
        )
    )
    return RunSummary(
        **state.counts,
        cost_usd=state.cost_usd,
        budget_stopped=state.counts["skipped_for_budget"] > 0,
        failures=tuple(state.failures),
    )
