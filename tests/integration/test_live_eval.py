"""End to end: `evalhawk init` + `evalhawk eval`, live judges, resume, labels and export."""

import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evalhawk.cli.main import app
from evalhawk.config import load_config
from evalhawk.core.errors import ConfigError
from evalhawk.core.models import Label, Outcome
from evalhawk.storage.sqlite import SQLiteStore
from evalhawk.testing.fake_llm import FakeLLMServer, chat_reply

runner = CliRunner(env={"COLUMNS": "200"})  # wide enough that tables never wrap
JUDGE_URL_LINE = '\nbase_url = "http://localhost:11434/v1"'  # the setting line, not the comment
QUICKSTART_CRITERIA = (
    'criteria = { not_empty = "code", concise = "code", no_personal_data = "code" }'
)


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    previous = Path.cwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(previous)


def _eval(*args: str) -> str:
    result = runner.invoke(app, ["eval", "--target-version", "v1", *args])
    assert result.exit_code == 0, result.stdout
    return result.stdout


def _db(project: Path) -> Path:
    return project / ".evalhawk" / "eval.db"


def _edit_config(project: Path, old: str, new: str) -> None:
    path = project / "evalhawk.toml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def _verdicts(project: Path, criterion: str) -> list[str]:
    with sqlite3.connect(_db(project)) as connection:
        criterion_ids = [
            row[0]
            for row in connection.execute("SELECT id, record FROM criteria")
            if json.loads(row[1])["name"] == criterion
        ]
        return [
            row[0]
            for row in connection.execute(
                "SELECT outcome FROM verdicts WHERE criterion_id = ?", (criterion_ids[0],)
            )
        ]


def test_init_refuses_to_overwrite(project: Path) -> None:
    result = runner.invoke(app, ["init", str(project)])
    assert result.exit_code == 1
    assert "--force" in result.stdout


def test_quickstart_runs_offline_with_code_checks(project: Path) -> None:
    out = _eval()
    assert "Starting run" in out
    assert "Judged pass rates" in out
    for criterion in ("not_empty", "concise", "no_personal_data"):
        assert criterion in out
    assert _verdicts(project, "not_empty") == ["PASS"] * 8
    # The bot's keyword matching misses 4 of 8 questions ("ship" isn't "shipping", "open"
    # isn't "hours"...), and its fallback reply contains an e-mail address: PII flags all 4.
    assert _verdicts(project, "no_personal_data").count("FAIL") == 4


def test_rerun_resumes_without_new_work(project: Path) -> None:
    _eval()
    out = _eval()
    assert "Resuming run" in out
    with sqlite3.connect(_db(project)) as connection:
        assert connection.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM traces").fetchone()[0] == 8
    fresh = _eval("--fresh")
    assert "Starting run" in fresh


def test_llm_judged_eval_then_labels_feed_judge_status(
    project: Path, llm_server: FakeLLMServer
) -> None:
    llm_server.respond = lambda _p: (200, chat_reply("Looks right.\nVERDICT: PASS"))
    _edit_config(project, JUDGE_URL_LINE, f'\nbase_url = "{llm_server.url}"')
    _edit_config(
        project,
        QUICKSTART_CRITERIA,
        'criteria = { concise = "code", correctness = "local", polite = "local" }',
    )
    out = _eval()
    assert "not calibrated yet" in out
    assert len(llm_server.requests) == 16  # 8 questions x 2 LLM-judged criteria
    _eval()
    assert len(llm_server.requests) == 16  # resumed: no new judge calls

    # add human labels to every answer (as the labelling UI does), then check status
    store = SQLiteStore(_db(project))
    try:
        run = store.find_runs("v1")[0]
        items = run.config_snapshot["criteria"]
        assert isinstance(items, list)
        polite = next(
            i["criterion_id"] for i in items if isinstance(i, dict) and i["name"] == "polite"
        )
        example_ids = [row[0] for row in store._connection.execute("SELECT id FROM examples")]
        for example_id in example_ids:
            trace = store.get_trace_slot(run.id, example_id, 0)
            assert trace is not None
            store.add_label(
                Label(
                    trace_id=trace.id,
                    criterion_id=str(polite),
                    outcome=Outcome.PASS,
                    annotator="tester",
                )
            )
    finally:
        store.close()
    status = runner.invoke(app, ["judges", "status", "--run", "v1"])
    assert status.exit_code == 0, status.stdout
    assert "polite" in status.stdout
    assert "insufficient" in status.stdout  # PASS labels only, no FAIL labels yet
    assert "exact (no calibration" in status.stdout


def test_export_writes_every_answer(project: Path) -> None:
    _eval()
    out = project / "export.jsonl"
    result = runner.invoke(app, ["export", "--run", "v1", "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 8
    assert {"input", "output", "split", "concise[code].judge"} <= set(rows[0])
    csv_out = project / "export.csv"
    assert runner.invoke(app, ["export", "--run", "v1", "--out", str(csv_out)]).exit_code == 0
    assert csv_out.read_text(encoding="utf-8").count("\n") == 9  # header + 8 rows


def test_sample_evaluates_a_reproducible_subset(project: Path) -> None:
    assert "3 examples" in _eval("--sample", "3")


def test_secrets_never_reach_the_database(
    project: Path, llm_server: FakeLLMServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUPER_SECRET", "sk-do-not-store")
    _edit_config(
        project,
        JUDGE_URL_LINE,
        f'\nbase_url = "{llm_server.url}"\nheaders = {{ X-Api-Key = "${{SUPER_SECRET}}" }}',
    )
    _edit_config(project, QUICKSTART_CRITERIA, 'criteria = { polite = "local" }')
    _eval()
    assert llm_server.headers[0]["x-api-key"] == "sk-do-not-store"  # used for the call...
    assert b"sk-do-not-store" not in _db(project).read_bytes()  # ...but never stored


# ------------------------------------------------------------- config safety
def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_config_errors_are_caught_before_any_call(tmp_path: Path) -> None:
    base = '[target]\ntype = "recorded"\n[[criteria]]\nname = "c"\nquestion = "Q?"\n'
    evaluation = '[evaluations.e]\ndataset = "d.jsonl"\n'
    with pytest.raises(ConfigError, match="unknown judge 'nope'"):
        load_config(_write(tmp_path / "a.toml", base + evaluation + 'criteria = { c = "nope" }\n'))
    with pytest.raises(ConfigError, match="unknown criterion 'missing'"):
        load_config(
            _write(tmp_path / "b.toml", base + evaluation + 'criteria = { missing = "code" }\n')
        )
    with pytest.raises(ConfigError, match="needs an LLM or function judge"):
        load_config(_write(tmp_path / "c.toml", base + evaluation + 'criteria = { c = "code" }\n'))
    with pytest.raises(ConfigError, match="exactly one of question, template or check"):
        load_config(
            _write(
                tmp_path / "d.toml",
                '[[criteria]]\nname = "x"\nquestion = "Q?"\ntemplate = "correctness"\n',
            )
        )
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(_write(tmp_path / "e.toml", "this is = = not toml"))


def test_rag_template_requires_a_rag_evaluation(project: Path, llm_server: FakeLLMServer) -> None:
    path = project / "evalhawk.toml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n[[criteria]]\nname = "grounded"\ntemplate = "faithfulness"\n',
        encoding="utf-8",
    )
    _edit_config(project, QUICKSTART_CRITERIA, 'criteria = { grounded = "local" }')
    result = runner.invoke(app, ["eval", "--target-version", "v1"])
    assert result.exit_code == 1
    assert 'set kind = "rag"' in result.stdout
    assert llm_server.requests == []


def test_missing_reference_is_caught_before_any_call(
    project: Path, llm_server: FakeLLMServer
) -> None:
    data = project / "data" / "questions.jsonl"
    data.write_text(
        data.read_text(encoding="utf-8") + '{"input": "no reference here"}\n', encoding="utf-8"
    )
    _edit_config(project, JUDGE_URL_LINE, f'\nbase_url = "{llm_server.url}"')
    _edit_config(project, QUICKSTART_CRITERIA, 'criteria = { correctness = "local" }')
    result = runner.invoke(app, ["eval", "--target-version", "v1"])
    assert result.exit_code == 1
    assert "need a reference answer" in result.stdout
    assert llm_server.requests == []
