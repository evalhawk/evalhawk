"""The shipped examples run offline, end to end, so they cannot silently rot."""

import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evalhawk.cli._shared import console
from evalhawk.cli.main import app

runner = CliRunner()
EXAMPLES = Path(__file__).parents[2] / "examples"
USER_MODULES = ("app", "judges")


@pytest.fixture(autouse=True)
def wide_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(console, "width", 200)


@pytest.fixture(autouse=True)
def fresh_user_modules() -> Iterator[None]:
    """Examples import top-level ``app``/``judges``; never leak them into other tests."""
    for module in USER_MODULES:
        sys.modules.pop(module, None)
    yield
    for module in USER_MODULES:
        sys.modules.pop(module, None)


@pytest.fixture
def rag_example(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "rag-support"
    shutil.copytree(EXAMPLES / "rag-support", folder)
    monkeypatch.chdir(folder)
    return folder


def test_rag_example_evaluates_answers_and_retrieval(rag_example: Path) -> None:
    result = runner.invoke(app, ["eval", "-t", "v1"])
    assert result.exit_code == 0, result.stdout
    assert "grounded_numbers" in result.stdout
    assert "90.0%" in result.stdout  # the invented "5 points per dollar" answer fails

    result = runner.invoke(app, ["retrieval", "--run", "v1", "--k", "2"])
    assert result.exit_code == 0, result.stdout
    assert "Retrieval quality (9 queries)" in result.stdout
    assert "0.778" in result.stdout  # two of nine questions retrieve nothing relevant


def test_quickstart_from_init_runs_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["eval", "-t", "v1"])
    assert result.exit_code == 0, result.stdout
    assert "no_personal_data" in result.stdout
    assert "50.0%" in result.stdout  # the fallback reply leaks support@example.com
