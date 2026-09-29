"""Smoke tests: the package installs, imports and exposes its CLI."""

from importlib.metadata import version

from typer.testing import CliRunner

import evalhawk
from evalhawk.cli.main import app

runner = CliRunner()


def test_version_matches_installed_metadata() -> None:
    assert evalhawk.__version__ == version("evalhawk")


def test_cli_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"evalhawk {evalhawk.__version__}"


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "evalhawk" in result.stdout.lower()
