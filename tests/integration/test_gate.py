"""`evalhawk gate` exit codes and `compare --corrected` on the synthetic demo."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from evalhawk.cli._shared import console
from evalhawk.cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def wide_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(console, "width", 200)


@pytest.fixture(scope="module")
def demo_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("gate")
    # the full demo (1,000 cases): smaller samples make the billing regression
    # statistically inconclusive, which is correct but not what this test exercises
    assert runner.invoke(app, ["demo", "init", str(folder)]).exit_code == 0
    db = folder / "state.db"
    for version in ("v1", "v2"):
        result = runner.invoke(
            app,
            [
                "import",
                str(folder / f"{version}.jsonl"),
                "--target-version",
                version,
                "--db",
                str(db),
            ],
        )
        assert result.exit_code == 0, result.stdout
    return db


def _gate(db: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(
        app, ["gate", "--baseline", "v1", "--candidate", "v2", "--db", str(db), *args]
    )
    return result.exit_code, result.stdout


def test_regression_fails_the_gate(demo_db: Path) -> None:
    code, out = _gate(demo_db, "--tag", "billing", "--n-boot", "500")
    assert code == 1  # v2 regresses on billing in the demo
    assert "GATE FAILED: WORSE" in out


def test_no_significant_regression_passes(demo_db: Path) -> None:
    code, out = _gate(demo_db, "--tag", "shipping", "--n-boot", "500")
    assert code == 0
    assert "GATE PASSED" in out


def test_inconclusive_can_be_made_to_fail(demo_db: Path) -> None:
    code, out = _gate(demo_db, "--n-boot", "500")
    assert code == 0  # overall the demo's difference is not significant (seed 0)
    assert "GATE PASSED: INCONCLUSIVE" in out
    strict, strict_out = _gate(demo_db, "--n-boot", "500", "--fail-on", "inconclusive")
    assert strict == 1
    assert "GATE FAILED: INCONCLUSIVE" in strict_out


def test_errors_exit_with_code_2(demo_db: Path) -> None:
    assert _gate(demo_db, "--fail-on", "sometimes")[0] == 2
    unknown_run = runner.invoke(
        app, ["gate", "--baseline", "v1", "--candidate", "nope", "--db", str(demo_db)]
    )
    assert unknown_run.exit_code == 2
    assert "found 0 executions" in unknown_run.stdout


def test_corrected_compare_shows_both_numbers(demo_db: Path) -> None:
    result = runner.invoke(
        app,
        [
            "compare",
            "--baseline",
            "v1",
            "--candidate",
            "v2",
            "--db",
            str(demo_db),
            "--corrected",
            "--n-boot",
            "500",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Judged (uncorrected)" in result.stdout
    assert "Corrected for the judge" in result.stdout
    assert "paired_rogan_gladen+bootstrap" in result.stdout
    code, out = _gate(demo_db, "--corrected", "--tag", "billing", "--n-boot", "500")
    assert code == 1
    assert "Corrected for the judge" in out
