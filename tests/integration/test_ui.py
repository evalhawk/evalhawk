"""The web UI: dashboard, blind labelling (never shows the judge), reports, safety."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evalhawk.core.models import Criterion, Example, Outcome, TargetOutput, Trace, Verdict
from evalhawk.core.splits import SplitSet
from evalhawk.runner.executor import JudgeSpec
from evalhawk.services.evaluate import find_or_create_run, run_evaluation, run_snapshot
from evalhawk.storage.sqlite import SQLiteStore
from evalhawk.testing.fakes import FakeTarget
from evalhawk.ui.app import create_app

SECRET_REASONING = "JUDGE-PRIVATE-REASONING-XYZ"
CRITERION = Criterion(name="helpful", question="Is the answer helpful?")


class KeywordJudge:
    """PASS when the answer says 'good'; always leaves a reasoning we must never show."""

    judge_id = "keyword-judge-v1"

    async def judge(self, example: Example, trace: Trace, criterion: Criterion) -> Verdict:
        return Verdict(
            trace_id=trace.id,
            criterion_id=criterion.id,
            judge_id=self.judge_id,
            outcome=Outcome.PASS if "good" in trace.output else Outcome.FAIL,
            reasoning=SECRET_REASONING,
        )


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Path, str]:
    db = tmp_path / "ui.db"
    examples = [Example(input=f"Question number {i}?") for i in range(80)]
    outputs = {
        e.id: TargetOutput(output="a good answer" if i % 3 else "a bad answer")
        for i, e in enumerate(examples)
    }
    splits = SplitSet(salt="ui-test")
    spec = JudgeSpec(CRITERION, KeywordJudge())
    snapshot = run_snapshot(
        evaluation="support",
        specs=[spec],
        judge_names=["keyword"],
        splits=splits,
        repeats=1,
        kind="single_turn",
        target={"type": "recorded"},
    )
    store = SQLiteStore(db)
    try:
        run, _ = find_or_create_run(store, target_version="v1", snapshot=snapshot)
        asyncio.run(
            run_evaluation(
                store,
                run=run,
                examples=examples,
                target=FakeTarget(outputs),
                specs=[spec],
                splits=splits,
            )
        )
    finally:
        store.close()
    return db, run.id


def _client(db: Path) -> TestClient:
    return TestClient(create_app(db, annotator="tester"))


def test_dashboard_and_run_pages(setup: tuple[Path, str]) -> None:
    db, run_id = setup
    client = _client(db)
    index = client.get("/")
    assert index.status_code == 200
    assert run_id[:12] in index.text
    run = client.get(f"/runs/{run_id}")
    assert run.status_code == 200
    assert "helpful" in run.text
    assert "needs ~20 more labels" in run.text


def test_labelling_is_blind_and_advances(setup: tuple[Path, str]) -> None:
    db, run_id = setup
    client = _client(db)
    page = client.get(f"/label/{run_id}/helpful")
    assert page.status_code == 200
    assert "Is the answer helpful?" in page.text
    assert "Answer to evaluate" in page.text
    # blind: no judge reasoning, verdict or judge identity anywhere on the page
    assert SECRET_REASONING not in page.text
    assert "keyword-judge" not in page.text
    assert "0 of" in page.text

    trace_id = page.text.split('name="trace_id" value="')[1].split('"')[0]
    reply = client.post(
        f"/label/{run_id}/helpful",
        content=f"trace_id={trace_id}&outcome=PASS&note=clear",
        headers={"HX-Request": "true", "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert reply.status_code == 200
    assert "1 of" in reply.text
    assert "<html" not in reply.text  # an htmx partial, not a whole page
    assert trace_id not in reply.text  # moved on to the next answer
    assert SECRET_REASONING not in reply.text

    store = SQLiteStore(db)
    try:
        labels = store._connection.execute("SELECT record FROM labels").fetchall()
    finally:
        store.close()
    assert len(labels) == 1
    assert '"annotator":"tester"' in labels[0][0]
    assert '"note":"clear"' in labels[0][0]


def test_cross_site_posts_and_bad_outcomes_are_refused(setup: tuple[Path, str]) -> None:
    db, run_id = setup
    client = _client(db)
    evil = client.post(
        f"/label/{run_id}/helpful",
        content="trace_id=x&outcome=PASS",
        headers={
            "Origin": "https://evil.example",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    assert evil.status_code == 403
    bad = client.post(
        f"/label/{run_id}/helpful",
        content="trace_id=x&outcome=MAYBE",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert bad.status_code == 400


def test_report_needs_labels_then_shows_corrected_rates(setup: tuple[Path, str]) -> None:
    db, run_id = setup
    client = _client(db)
    assert "Not enough data" in client.get(f"/report/{run_id}/helpful").text
    # label every dev answer with the truth (good answers are good)
    for _ in range(200):
        page = client.get(f"/label/{run_id}/helpful").text
        if 'name="trace_id"' not in page:
            break
        trace_id = page.split('name="trace_id" value="')[1].split('"')[0]
        answer = page.split("Answer to evaluate</div>")[1]
        outcome = "PASS" if "a good answer" in answer.split("</pre>")[0] else "FAIL"
        client.post(
            f"/label/{run_id}/helpful",
            content=f"trace_id={trace_id}&outcome={outcome}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
    assert "All" in client.get(f"/label/{run_id}/helpful").text
    report = client.get(f"/report/{run_id}/helpful")
    assert report.status_code == 200
    assert "Judge report card" in report.text
    assert "Corrected: PPI" in report.text
    assert "100.0%" in report.text  # this judge agrees with every label


def test_unknown_run_shows_a_friendly_error(setup: tuple[Path, str]) -> None:
    db, _ = setup
    page = _client(db).get("/runs/nope")
    assert page.status_code == 200
    assert "no run nope" in page.text
