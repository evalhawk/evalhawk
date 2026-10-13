import sqlite3
import time
from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

import pytest

from evalhawk.core.errors import DataError, StoreError
from evalhawk.core.models import Criterion, Example, Label, Outcome, Run, Split, Trace, Verdict
from evalhawk.core.protocols import Store
from evalhawk.core.splits import SplitSet
from evalhawk.storage.sqlite import SQLiteStore
from evalhawk.testing.fakes import InMemoryStore


@pytest.fixture(params=["sqlite", "memory"])
def store(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[Store]:
    result: Store = (
        SQLiteStore(tmp_path / "state.db") if request.param == "sqlite" else InMemoryStore()
    )
    yield result
    result.close()


def test_store_round_trip_pairs_and_reimport(store: Store) -> None:
    example = Example(input="refund?", group_id="seed-1", tags=("billing",))
    run = Run(target_version="v1")
    criterion = Criterion(name="correct", question="Is it correct?")
    config = SplitSet(ratios=(0, 0, 1))
    trace = Trace(example_id=example.id, run_id=run.id, output="yes")
    verdict = Verdict(
        trace_id=trace.id, criterion_id=criterion.id, judge_id="judge", outcome=Outcome.PASS
    )
    label = Label(
        trace_id=trace.id, criterion_id=criterion.id, outcome=Outcome.FAIL, annotator="human"
    )
    for _ in range(2):
        store.add_examples([example])
        store.assign_splits(config, [example])
        store.add_traces(run, [trace])
        store.add_criterion(criterion)
        store.put_verdict(verdict)
        store.add_label(label)
    assert store.get_verdict(trace.id, criterion.id, "judge") == verdict
    rows = list(
        store.paired_records(
            run_id=run.id,
            criterion_id=criterion.id,
            judge_id="judge",
            split_set_id=config.id,
            split=Split.TEST,
            purpose="test",
            tag="billing",
        )
    )
    assert len(rows) == 1
    assert rows[0].human == Outcome.FAIL
    assert store.split_counts(config.id, tag="billing")[Split.TEST] == 1
    lean = list(
        store.outcome_rows(
            run_id=run.id,
            criterion_id=criterion.id,
            judge_id="judge",
            split_set_id=config.id,
            split=Split.TEST,
            purpose="lean read",
            tag="billing",
        )
    )
    assert len(lean) == 1
    assert lean[0].label_time == label.created_at
    assert lean[0].human == Outcome.FAIL
    assert store.find_runs("v1") == [run]
    assert store.get_run(run.id) == run
    assert store.get_run("missing") is None
    assert len(store.test_reads(config.id)) == 2


def test_group_changes_and_config_changes_refused(store: Store) -> None:
    first = Example(input="refund?")
    changed = Example(input="refund?", group_id="seed-1")
    config = SplitSet()
    store.add_examples([first])
    store.assign_splits(config, [first])
    with pytest.raises(DataError, match="group"):
        store.assign_splits(config, [changed])
    with pytest.raises(DataError, match="salt"):
        store.assign_splits(SplitSet(ratios=(0.3, 0.3, 0.4)), [first])
    store.assign_splits(SplitSet(salt="v2"), [first])
    assert store.get_split(config.id, first.id) == config.assign(first)


def test_lean_reads_count_missing_judgments(store: Store) -> None:
    example = Example(input="missing judgment")
    run = Run(target_version="v1")
    criterion = Criterion(name="correct", question="Correct?")
    config = SplitSet(ratios=(0, 0, 1))
    trace = Trace(example_id=example.id, run_id=run.id, output="answer")
    store.add_examples([example])
    store.assign_splits(config, [example])
    store.add_traces(run, [trace])
    store.add_criterion(criterion)
    store.add_label(
        Label(
            trace_id=trace.id, criterion_id=criterion.id, outcome=Outcome.PASS, annotator="reviewer"
        )
    )
    rows = list(
        store.outcome_rows(
            run_id=run.id,
            criterion_id=criterion.id,
            judge_id="missing",
            split_set_id=config.id,
            split=Split.TEST,
            purpose="missing check",
        )
    )
    assert len(rows) == 1
    assert rows[0].judge_missing
    assert rows[0].human == Outcome.PASS
    blind_rows = list(
        store.outcome_rows(
            run_id=run.id,
            criterion_id=criterion.id,
            judge_id="missing",
            split_set_id=config.id,
            split=Split.TEST,
            purpose="judge-only check",
            include_labels=False,
        )
    )
    assert blind_rows[0].human is None
    assert blind_rows[0].label_time is None
    assert blind_rows[0].judge_missing


def test_populated_schema_one_upgrade(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    example = Example(input="question")
    run = Run(target_version="old")
    criterion = Criterion(name="correct", question="Correct?")
    trace = Trace(example_id=example.id, run_id=run.id, output="answer")
    verdict = Verdict(
        trace_id=trace.id, criterion_id=criterion.id, judge_id="judge", outcome=Outcome.PASS
    )
    label = Label(
        trace_id=trace.id, criterion_id=criterion.id, annotator="human", outcome=Outcome.FAIL
    )
    with sqlite3.connect(path) as connection:
        script = files("evalhawk.storage").joinpath("migrations/0001_init.sql").read_text()
        connection.executescript(script)
        connection.execute(
            "INSERT INTO examples VALUES (?,?)", (example.id, example.model_dump_json())
        )
        connection.execute("INSERT INTO runs VALUES (?,?)", (run.id, run.model_dump_json()))
        connection.execute(
            "INSERT INTO criteria VALUES (?,?)", (criterion.id, criterion.model_dump_json())
        )
        connection.execute(
            "INSERT INTO traces VALUES (?,?,?,?,?)",
            (trace.id, example.id, run.id, 0, trace.model_dump_json()),
        )
        connection.execute(
            "INSERT INTO verdicts VALUES (?,?,?,?)",
            (trace.id, criterion.id, "judge", verdict.model_dump_json()),
        )
        connection.execute(
            "INSERT INTO labels VALUES (?,?,?,?)",
            (label.id, trace.id, criterion.id, label.model_dump_json()),
        )
        connection.execute("PRAGMA user_version=1")
    with SQLiteStore(path) as store:
        config = SplitSet(ratios=(0, 0, 1))
        store.assign_splits(config, [example])
        rows = list(
            store.outcome_rows(
                run_id=run.id,
                criterion_id=criterion.id,
                judge_id="judge",
                split_set_id=config.id,
                split=Split.TEST,
                purpose="upgrade check",
            )
        )
        assert rows[0].human == Outcome.FAIL
        assert rows[0].label_time == label.created_at
        assert store.get_verdict(trace.id, criterion.id, "judge") == verdict


def test_sql_split_triggers_and_test_access_log(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    example = Example(input="question")
    config = SplitSet(ratios=(0, 0, 1))
    with SQLiteStore(path) as database:
        database.add_examples([example])
        database.assign_splits(config, [example])
        list(
            database.paired_records(
                run_id="none",
                criterion_id="none",
                judge_id="none",
                split_set_id=config.id,
                split=Split.TEST,
                purpose="audit",
            )
        )
    with sqlite3.connect(path) as connection:
        for statement in (
            "UPDATE splits SET split='train'",
            "DELETE FROM splits",
            "UPDATE split_sets SET salt='new'",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(statement)
        assert connection.execute("SELECT count(*) FROM test_access_log").fetchone()[0] == 1
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_batch_is_atomic_on_missing_reference(store: Store) -> None:
    run = Run(target_version="v1")
    with pytest.raises(StoreError):
        store.add_traces(run, [Trace(example_id="missing", run_id=run.id, output="answer")])


def test_new_group_members_and_changed_group_history(store: Store) -> None:
    first = Example(input="refund?", group_id="seed-1")
    new = Example(input="money back?", group_id="seed-1")
    config = SplitSet()
    store.add_examples([first, new])
    store.assign_splits(config, [first])
    store.assign_splits(config, [new])
    assert store.get_split(config.id, first.id) == store.get_split(config.id, new.id)
    changed = Example(input="refund?", group_id="seed-2")
    store.add_examples([changed])
    newer = SplitSet(salt="v2")
    store.assign_splits(newer, [changed])
    with pytest.raises(DataError, match="group"):
        store.assign_splits(config, [changed])
    assert store.get_split(config.id, first.id) == config.assign(first)


def test_conflicting_trace_slot_refused(store: Store) -> None:
    example = Example(input="question")
    run = Run(target_version="v1")
    store.add_examples([example])
    store.add_traces(run, [Trace(example_id=example.id, run_id=run.id, output="first")])
    with pytest.raises(DataError, match="slot"):
        store.add_traces(run, [Trace(example_id=example.id, run_id=run.id, output="second")])


def test_two_connections_read_during_wal_write(tmp_path: Path) -> None:
    path = tmp_path / "concurrent.db"
    with SQLiteStore(path), sqlite3.connect(path) as writer, sqlite3.connect(path) as reader:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO examples VALUES ('pending', '{}')")
        assert reader.execute("SELECT count(*) FROM examples").fetchone()[0] == 0
        writer.rollback()


def test_duplicate_batch_tags_replace_previous_tags(store: Store) -> None:
    first = Example(input="same", tags=("old",))
    last = Example(input="same", tags=("new",))
    config = SplitSet(ratios=(0, 0, 1))
    store.add_examples([first, last])
    store.assign_splits(config, [last])
    assert store.split_counts(config.id, tag="old")[Split.TEST] == 0
    assert store.split_counts(config.id, tag="new")[Split.TEST] == 1


def test_locked_snapshot_and_multiple_unknown_annotations(store: Store) -> None:
    example = Example(input="same", group_id="original")
    changed = Example(input="same", group_id="updated")
    config = SplitSet(by="example_id", ratios=(0, 0, 1))
    run = Run(target_version="v1")
    criterion = Criterion(name="correct", question="Correct?")
    trace = Trace(example_id=example.id, run_id=run.id, output="answer")
    store.add_examples([example])
    store.assign_splits(config, [example])
    store.add_examples([changed])
    store.assign_splits(config, [changed])
    store.add_traces(run, [trace])
    store.add_criterion(criterion)
    verdict = Verdict(
        trace_id=trace.id, criterion_id=criterion.id, judge_id="judge", outcome=Outcome.UNKNOWN
    )
    store.put_verdict(verdict)
    with pytest.raises(DataError, match="cached"):
        store.put_verdict(verdict.model_copy(update={"outcome": Outcome.PASS}))
    for outcome in (Outcome.PASS, Outcome.UNKNOWN):
        store.add_label(
            Label(trace_id=trace.id, criterion_id=criterion.id, outcome=outcome, annotator="human")
        )
    rows = list(
        store.paired_records(
            run_id=run.id,
            criterion_id=criterion.id,
            judge_id="judge",
            split_set_id=config.id,
            split=Split.TEST,
            purpose="regression",
        )
    )
    assert len(rows) == 2
    assert {row.human for row in rows} == {Outcome.PASS, Outcome.UNKNOWN}
    assert all(row.judge == Outcome.UNKNOWN and row.group_id == "original" for row in rows)


def test_sqlite_rejects_newer_schema_and_wraps_open_failure(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=3")
    with pytest.raises(StoreError, match="newer"):
        SQLiteStore(path)
    with pytest.raises(StoreError, match="cannot open"):
        SQLiteStore(tmp_path / "missing" / "state.db")


@pytest.mark.slow
def test_twenty_thousand_example_inserts_under_one_second(tmp_path: Path) -> None:
    examples = [Example(input=f"question {index}") for index in range(20_000)]
    with SQLiteStore(tmp_path / "benchmark.db") as database:
        start = time.perf_counter()
        database.add_examples(examples)
        elapsed = time.perf_counter() - start
    assert elapsed < 1, f"20,000 inserts took {elapsed:.3f}s"
