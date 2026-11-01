"""`evalhawk discover`: cluster failure reasons and (optionally) name them with an LLM."""

import asyncio
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evalhawk.cli._shared import console
from evalhawk.cli.main import app
from evalhawk.core.models import Criterion, Example, Label, Outcome, TargetOutput, Trace, Verdict
from evalhawk.core.splits import SplitSet
from evalhawk.runner.executor import JudgeSpec
from evalhawk.services.evaluate import find_or_create_run, run_evaluation, run_snapshot
from evalhawk.storage.sqlite import SQLiteStore
from evalhawk.testing.fake_llm import FakeLLMServer, chat_reply
from evalhawk.testing.fakes import FakeTarget

runner = CliRunner()
CRITERION = Criterion(name="correct", question="Is the answer correct?")
REASONS = [
    "claims refunds take 60 days, policy says 30 days",
    "claims refunds take 90 days, policy says 30 days",
    "invents a loyalty programme with gold points",
    "invents a loyalty programme with bonus points",
]


@pytest.fixture(autouse=True)
def wide_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(console, "width", 200)


class ReasonJudge:
    judge_id = "reason-judge"

    async def judge(self, example: Example, trace: Trace, criterion: Criterion) -> Verdict:
        index = int(trace.output.split()[-1])
        failed = index < len(REASONS)
        return Verdict(
            trace_id=trace.id,
            criterion_id=criterion.id,
            judge_id=self.judge_id,
            outcome=Outcome.FAIL if failed else Outcome.PASS,
            reasoning=REASONS[index] if failed else "fine",
        )


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "d.db"
    examples = [Example(input=f"q{i}") for i in range(8)]
    outputs = {e.id: TargetOutput(output=f"answer {i}") for i, e in enumerate(examples)}
    splits = SplitSet(salt="discover")
    spec = JudgeSpec(CRITERION, ReasonJudge())
    snapshot = run_snapshot(
        evaluation="e",
        specs=[spec],
        judge_names=["llm"],
        splits=splits,
        repeats=1,
        kind="single_turn",
        target={"type": "recorded"},
    )
    store = SQLiteStore(path)
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
        trace = store.get_trace_slot(run.id, examples[5].id, 0)
        assert trace is not None
        store.add_label(
            Label(
                trace_id=trace.id,
                criterion_id=CRITERION.id,
                annotator="h",
                outcome=Outcome.FAIL,
                note="rude tone towards the customer",
            )
        )
    finally:
        store.close()
    return path


def test_discover_clusters_judge_reasoning_and_human_notes(db: Path) -> None:
    result = runner.invoke(app, ["discover", "--run", "v1", "--db", str(db), "--k", "2"])
    assert result.exit_code == 0, result.stdout
    assert "5 failure reasons in 2 clusters" in result.stdout
    assert "loyalty" in result.stdout
    assert "refunds" in result.stdout or "days" in result.stdout


def test_discover_names_clusters_with_an_llm(
    db: Path, tmp_path: Path, llm_server: FakeLLMServer
) -> None:
    llm_server.respond = lambda _p: (
        200,
        chat_reply(
            "NAME: no_invented_programmes\nQUESTION: Is the answer free of invented programmes?"
        ),
    )
    config = tmp_path / "evalhawk.toml"
    config.write_text(
        f'[judges.namer]\ntype = "openai_compatible"\nbase_url = "{llm_server.url}"\nmodel = "m"\n',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "discover",
            "--run",
            "v1",
            "--db",
            str(db),
            "--k",
            "2",
            "--namer",
            "namer",
            "--config",
            str(config),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "NAME: no_invented_programmes" in result.stdout
    assert len(llm_server.requests) == 2  # one proposal per cluster


def test_discover_needs_failure_reasons(tmp_path: Path) -> None:
    empty = tmp_path / "empty.db"
    SQLiteStore(empty).close()
    result = runner.invoke(app, ["discover", "--run", "v1", "--db", str(empty)])
    assert result.exit_code == 1
