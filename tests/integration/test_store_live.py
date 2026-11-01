"""Store capabilities needed by live evaluation (Phase 4): resume and the judgment cache."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from evalhawk.core.models import Criterion, Example, Outcome, Run, Trace, Verdict, judgment_key
from evalhawk.core.protocols import Store
from evalhawk.storage.sqlite import SQLiteStore
from evalhawk.testing.fakes import InMemoryStore


@pytest.fixture(params=["sqlite", "memory"])
def store(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[Store]:
    result: Store = (
        SQLiteStore(tmp_path / "state.db") if request.param == "sqlite" else InMemoryStore()
    )
    yield result
    result.close()


def _setup(store: Store) -> tuple[Example, Run, Trace, Criterion]:
    example = Example(input="What's your refund policy?", reference="30 days")
    run = Run(target_version="v1")
    trace = Trace(example_id=example.id, run_id=run.id, output="Refunds within 30 days.")
    criterion = Criterion(name="correct", question="Is it correct?")
    store.add_examples([example])
    store.add_traces(run, [trace])
    store.add_criterion(criterion)
    return example, run, trace, criterion


def test_lookups_by_id(store: Store) -> None:
    example, _, trace, criterion = _setup(store)
    assert store.get_example(example.id) == example
    assert store.get_trace(trace.id) == trace
    assert store.get_criterion(criterion.id) == criterion
    assert store.get_example("missing") is None
    assert store.get_trace("missing") is None
    assert store.get_criterion("missing") is None


def test_trace_slot_lookup_supports_resume(store: Store) -> None:
    example, run, trace, _ = _setup(store)
    assert store.get_trace_slot(run.id, example.id, 0) == trace
    assert store.get_trace_slot(run.id, example.id, 1) is None
    assert store.get_trace_slot("other-run", example.id, 0) is None


def test_judgment_cache_round_trip(store: Store) -> None:
    example, _, trace, criterion = _setup(store)
    key = judgment_key(example, trace, criterion, "judge-a")
    assert store.get_judgment(key) is None
    verdict = Verdict(
        trace_id=trace.id,
        criterion_id=criterion.id,
        judge_id="judge-a",
        outcome=Outcome.PASS,
        probability=0.9,
        reasoning="Matches the reference.",
    )
    store.put_judgment(key, verdict)
    store.put_judgment(key, verdict)  # idempotent
    cached = store.get_judgment(key)
    assert cached is not None
    assert (cached.outcome, cached.probability, cached.reasoning) == (
        Outcome.PASS,
        0.9,
        "Matches the reference.",
    )


# ------------------------------------------------------------------ judgment key
def _trace(example: Example, run: str, output: str, repeat: int = 0) -> Trace:
    return Trace(example_id=example.id, run_id=run, output=output, repeat_index=repeat)


def test_judgment_key_ignores_run_and_repeat() -> None:
    example = Example(input="q")
    criterion = Criterion(name="c", question="Is it right?")
    a = judgment_key(example, _trace(example, "run-v1", "same answer"), criterion, "j")
    b = judgment_key(example, _trace(example, "run-v2", "same answer", repeat=3), criterion, "j")
    assert a == b  # the judge sees exactly the same thing


def test_judgment_key_changes_with_anything_the_judge_sees() -> None:
    example = Example(input="q", reference="r")
    criterion = Criterion(name="c", question="Is it right?")
    base = judgment_key(example, _trace(example, "run", "answer"), criterion, "j")
    other_example = Example(input="q", reference="different reference")
    with_contexts = Trace(example_id=example.id, run_id="run", output="answer", contexts=("doc",))
    keys = {
        judgment_key(example, _trace(example, "run", "other answer"), criterion, "j"),
        judgment_key(other_example, _trace(other_example, "run", "answer"), criterion, "j"),
        judgment_key(example, with_contexts, criterion, "j"),
        judgment_key(
            example, _trace(example, "run", "answer"), Criterion(name="c", question="Other?"), "j"
        ),
        judgment_key(example, _trace(example, "run", "answer"), criterion, "another-judge"),
    }
    assert base not in keys
    assert len(keys) == 5
