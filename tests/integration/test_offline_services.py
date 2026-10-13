import csv
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from evalhawk.core.errors import DataError, JudgeTooWeakError
from evalhawk.core.models import Criterion, Outcome, Run, Split
from evalhawk.core.protocols import OutcomeRow
from evalhawk.core.splits import SplitSet
from evalhawk.services.compare import compare
from evalhawk.services.estimate import adjudicate, report, representatives
from evalhawk.services.importing import import_recorded
from evalhawk.sources.verdicts import VerdictSource
from evalhawk.storage.sqlite import SQLiteStore


def test_recorded_import_and_resume(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text(
        json.dumps(
            {
                "input": "refund?",
                "output": "yes",
                "judge": "PASS",
                "labels": [{"annotator": "reviewer", "outcome": "FAIL"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run = Run(target_version="v1")
    criterion = Criterion(name="correct", question="Is it correct?")
    splits = SplitSet(ratios=(0, 0, 1))
    source = VerdictSource(path, run=run, criterion=criterion, judge_id="judge")
    with SQLiteStore(tmp_path / "state.db") as store:
        for _ in range(2):
            assert (
                import_recorded(store, source.load(), run=run, criterion=criterion, splits=splits)
                == 1
            )
        rows = list(
            store.outcome_rows(
                run_id=run.id,
                criterion_id=criterion.id,
                judge_id="judge",
                split_set_id=splits.id,
                split=Split.TEST,
                purpose="check",
            )
        )
        assert len(rows) == 1
        assert rows[0].label_time is not None


def test_bad_annotation_names_file_row_and_field(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"input":"q","output":"a","judge":"maybe"}\n', encoding="utf-8")
    source = VerdictSource(
        path,
        run=Run(target_version="v1"),
        criterion=Criterion(name="correct", question="Correct?"),
        judge_id="judge",
    )
    with pytest.raises(DataError, match=r"bad.jsonl: row 1, judge"):
        list(source.load())


def test_adjudication_latest_ties_and_unknown() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    first = OutcomeRow("example", None, "trace", 0, Outcome.PASS, Outcome.PASS, "reviewer", 1, at)
    assert adjudicate([first, replace(first, human=Outcome.FAIL)]) is None
    assert (
        adjudicate(
            [first, replace(first, human=Outcome.FAIL, label_time=at + timedelta(seconds=1))]
        )
        == Outcome.FAIL
    )
    assert (
        adjudicate([first, replace(first, annotator="other", human=Outcome.UNKNOWN)])
        == Outcome.PASS
    )
    assert adjudicate([first, replace(first, annotator="other", human=Outcome.FAIL)]) is None
    with pytest.raises(DataError, match="weighted"):
        adjudicate([replace(first, inclusion_prob=0.5)])


def test_rate_report_uses_dev_and_audits_test(tmp_path: Path) -> None:
    path = tmp_path / "many.jsonl"
    rng = np.random.default_rng(5)
    records = []
    for index in range(2000):
        human = rng.random() < 0.65
        judge = rng.random() < (0.94 if human else 0.35)
        records.append(
            json.dumps(
                {
                    "input": str(index),
                    "output": "answer",
                    "judge": "PASS" if judge else "FAIL",
                    "labels": [{"annotator": "human", "outcome": "PASS" if human else "FAIL"}],
                }
            )
        )
    path.write_text("\n".join(records), encoding="utf-8")
    run = Run(target_version="v1")
    criterion = Criterion(name="correct", question="Correct?")
    splits = SplitSet()
    with SQLiteStore(tmp_path / "state.db") as store:
        import_recorded(
            store,
            VerdictSource(path, run=run, criterion=criterion, judge_id="judge").load(),
            run=run,
            criterion=criterion,
            splits=splits,
        )
        result = report(
            store,
            run_id=run.id,
            criterion_id=criterion.id,
            judge_id="judge",
            split_set_id=splits.id,
            rng=np.random.default_rng(0),
            n_boot=100,
        )
        assert result.calibration_pairs > 500
        assert result.naive.point > result.corrected.point
        assert abs(result.ppi.point - 0.65) < 0.08
        assert len(store.test_reads(splits.id)) == 1


@pytest.mark.parametrize("grouped", [False, True])
def test_paired_proxy_comparison(tmp_path: Path, grouped: bool) -> None:
    criterion = Criterion(name="correct", question="Correct?")
    splits = SplitSet(ratios=(0, 0, 1))
    runs = [Run(target_version=version) for version in ("v1", "v2")]
    with SQLiteStore(tmp_path / "state.db") as store:
        for version_index, run in enumerate(runs):
            path = tmp_path / f"{run.target_version}.jsonl"
            records = [
                {
                    "input": str(index),
                    "output": run.target_version,
                    "group_id": str(index // 2) if grouped else None,
                    "judge": "PASS" if index % 10 < 5 + version_index else "FAIL",
                }
                for index in range(200)
            ]
            path.write_text("\n".join(map(json.dumps, records)), encoding="utf-8")
            import_recorded(
                store,
                VerdictSource(path, run=run, criterion=criterion, judge_id="judge").load(),
                run=run,
                criterion=criterion,
                splits=splits,
            )
        result = compare(
            store,
            baseline_id=runs[0].id,
            candidate_id=runs[1].id,
            criterion_id=criterion.id,
            judge_id="judge",
            split_set_id=splits.id,
            rng=np.random.default_rng(0),
            n_boot=100,
        )
        assert result.difference.point == pytest.approx(0.1)
        assert result.decision == "BETTER"
        assert (result.p_value is None) == grouped
        assert (result.required_total is None) == grouped
        assert len(store.test_reads(splits.id)) == 2


def test_csv_annotations_and_repeat(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["input", "output", "judge", "tags", "repeat_index", "labels"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "input": "q",
                "output": "a",
                "judge": "FAIL",
                "tags": "a|b",
                "repeat_index": "2",
                "labels": json.dumps(
                    [
                        {
                            "annotator": "human",
                            "outcome": "PASS",
                            "created_at": "2026-01-01T00:00:00Z",
                        }
                    ]
                ),
            }
        )
    source = VerdictSource(
        path,
        run=Run(target_version="v1"),
        criterion=Criterion(name="correct", question="Correct?"),
        judge_id="judge",
    )
    (record,) = source.load()
    assert record.trace.repeat_index == 2
    assert record.example.tags == ("a", "b")
    assert record.labels[0].outcome == Outcome.PASS


def test_partial_import_can_resume(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    good = '{"input":"q","output":"a","judge":"PASS"}\n'
    path.write_text(good + '{"input":"bad","output":"a","judge":"maybe"}\n')
    run = Run(target_version="v1")
    criterion = Criterion(name="correct", question="Correct?")
    splits = SplitSet(ratios=(0, 0, 1))
    source = VerdictSource(path, run=run, criterion=criterion, judge_id="judge")
    with SQLiteStore(tmp_path / "state.db") as store:
        with pytest.raises(DataError, match="row 2"):
            import_recorded(
                store, source.load(), run=run, criterion=criterion, splits=splits, batch_size=1
            )
        path.write_text(good)
        assert (
            import_recorded(
                store, source.load(), run=run, criterion=criterion, splits=splits, batch_size=1
            )
            == 1
        )
        rows = list(
            store.outcome_rows(
                run_id=run.id,
                criterion_id=criterion.id,
                judge_id="judge",
                split_set_id=splits.id,
                split=Split.TEST,
                purpose="resume",
            )
        )
        assert len(rows) == 1


def test_missing_verdict_does_not_change_group_representative() -> None:
    first = OutcomeRow("a", "group", "trace-a", 0, Outcome.UNKNOWN, None, None, None, None, True)
    second = replace(
        first, example_id="b", trace_id="trace-b", judge=Outcome.PASS, judge_missing=False
    )
    result = list(representatives([first, second], adjudicate_labels=False))
    assert len(result) == 1
    assert result[0][0].example_id == "a"
    assert result[0][0].judge_missing


def test_weak_judge_cli_error_is_actionable() -> None:
    import typer

    from evalhawk.cli.main import _user_errors

    with pytest.raises(typer.Exit) as captured, _user_errors():
        raise JudgeTooWeakError("judge too weak; improve calibration")
    assert captured.value.exit_code == 1
