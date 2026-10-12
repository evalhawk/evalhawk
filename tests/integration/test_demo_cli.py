import json
from pathlib import Path

from typer.testing import CliRunner

from evalhawk.cli.main import app


def test_offline_demo_workflow_and_resume(tmp_path: Path) -> None:
    runner = CliRunner()
    directory = tmp_path / "demo"
    database = tmp_path / "state.db"
    result = runner.invoke(app, ["demo", "init", str(directory), "--seed", "0"])
    assert result.exit_code == 0, result.output
    for version in ("v1", "v2"):
        command = [
            "import",
            str(directory / f"{version}.jsonl"),
            "--target-version",
            version,
            "--db",
            str(database),
        ]
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output
        manifest = json.loads((directory / f"{version}.run.json").read_text())
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output
        assert manifest["id"] in result.output
    (directory / "answer_key.json").unlink()
    command = ["report", "--run", "v1", "--db", str(database), "--n-boot", "100"]
    first = runner.invoke(app, command)
    second = runner.invoke(app, command)
    assert first.exit_code == 0, first.output
    assert first.output == second.output
    assert "Rogan-Gladen" in first.output
    assert "representative" in first.output
    result = runner.invoke(
        app,
        [
            "compare",
            "--baseline",
            "v1",
            "--candidate",
            "v2",
            "--db",
            str(database),
            "--n-boot",
            "100",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "cluster interval" in result.output
    result = runner.invoke(app, ["audit", "--run", "v1", "--db", str(database)])
    assert result.exit_code == 0, result.output
    assert "rate report" in result.output
    assert "paired proxy comparison" in result.output


def test_existing_demo_refused(tmp_path: Path) -> None:
    runner = CliRunner()
    arguments = ["demo", "init", str(tmp_path / "demo"), "--cases", "300"]
    assert runner.invoke(app, arguments).exit_code == 0
    result = runner.invoke(app, arguments)
    assert result.exit_code == 1
    assert "already exist" in result.output
