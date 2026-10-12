"""Entry point for the ``evalhawk`` command."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import numpy as np
import typer
from rich.console import Console
from rich.table import Table

from evalhawk import __version__
from evalhawk.core.errors import DataError, EvalhawkError
from evalhawk.core.models import Criterion, Run, Split
from evalhawk.core.protocols import Store
from evalhawk.core.results import Estimate
from evalhawk.core.splits import SplitSet
from evalhawk.services.compare import compare as compare_runs
from evalhawk.services.estimate import report as estimate_run
from evalhawk.services.importing import import_recorded
from evalhawk.testing.demo_data import generate_demo
from evalhawk.wiring import open_store, recorded_source

app = typer.Typer(
    name="evalhawk",
    help="Trustworthy LLM evaluation: calibrate judges, get honest numbers.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"evalhawk {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Calibrate LLM judges against humans and report bias-corrected results."""


console = Console(markup=False, highlight=False)
demo = typer.Typer(help="Generate an offline synthetic evaluation.", no_args_is_help=True)
app.add_typer(demo, name="demo")


@contextmanager
def _user_errors() -> Iterator[None]:
    try:
        yield
    except (EvalhawkError, ValueError, OSError) as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(code=1) from exc


def _select_run(store: Store, selection: str) -> Run:
    exact = store.get_run(selection)
    if exact:
        return exact
    matches = store.find_runs(selection)
    if len(matches) != 1:
        raise DataError(
            f"run {selection!r}: found {len(matches)} executions; supply an exact run ID"
        )
    return matches[0]


def _report_context(run: Run) -> tuple[str, str, SplitSet]:
    config = run.config_snapshot
    criterion_id = config.get("criterion_id")
    judge_id = config.get("judge_id")
    if not isinstance(criterion_id, str) or not isinstance(judge_id, str) or "splits" not in config:
        raise DataError("run has no recorded-import configuration; select an imported execution")
    return criterion_id, judge_id, SplitSet.model_validate(config["splits"])


def _estimate_table(title: str, rows: list[tuple[str, Estimate]]) -> None:
    table = Table(title=title)
    for heading in ("Metric", "Estimate", "Interval", "Confidence", "n", "Method"):
        table.add_column(heading)
    for label, result in rows:
        table.add_row(
            label,
            f"{result.point:.3f}",
            f"[{result.low:.3f}, {result.high:.3f}]",
            f"{result.confidence:.0%}",
            str(result.n),
            result.method,
        )
    console.print(table)


@demo.command("init")
def demo_init(
    directory: Path,
    seed: int = 0,
    cases: int = 1000,
    paraphrases: int = 3,
) -> None:
    """Write synthetic support-bot outputs and a separate answer key."""
    with _user_errors():
        generate_demo(directory, seed=seed, cases=cases, paraphrases=paraphrases)
        console.print(f"Synthetic demo: {cases} cases, {cases * paraphrases} outputs per version.")
        console.print(f"Created {directory / 'v1.jsonl'} and {directory / 'v2.jsonl'}")
        console.print("Answer key is separate; import/report/compare do not read it.")


@app.command("import")
def import_file(
    file: Path,
    target_version: Annotated[str, typer.Option("--target-version")],
    db: Annotated[Path, typer.Option("--db")],
    run_manifest: Annotated[Path | None, typer.Option("--run-manifest")] = None,
    criterion: str = "correct",
    question: str = "Is the response correct?",
    judge_id: str = "demo-judge",
    salt: str = "v1",
) -> None:
    """Import JSONL/CSV recorded outcomes; retain a run manifest for idempotent resume."""
    with _user_errors():
        criterion_record = Criterion(name=criterion, question=question)
        splits = SplitSet(salt=salt)
        manifest = run_manifest or file.with_suffix(".run.json")
        config = {
            "criterion_id": criterion_record.id,
            "judge_id": judge_id,
            "splits": splits.model_dump(mode="json"),
        }
        if manifest.exists():
            run = Run.model_validate_json(manifest.read_text(encoding="utf-8"))
            if run.target_version != target_version or run.config_snapshot != config:
                raise DataError(
                    "manifest configuration differs; select a new manifest for a new run"
                )
        else:
            run = Run(target_version=target_version, config_snapshot=config)
            manifest.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
        with open_store(db) as store:
            source = recorded_source(file, run=run, criterion=criterion_record, judge_id=judge_id)
            count = import_recorded(
                store, source.load(), run=run, criterion=criterion_record, splits=splits
            )
        console.print(f"Processed {count} rows. Run: {run.id}")
        console.print(f"Manifest: {manifest}; completed writes survive later import errors.")


@app.command("report")
def report_command(
    run: Annotated[str, typer.Option("--run")],
    db: Annotated[Path, typer.Option("--db")],
    tag: str | None = None,
    seed: int = 0,
    n_boot: int = 2000,
) -> None:
    """Judge report card and representative-case rates with confidence intervals."""
    with _user_errors(), open_store(db) as store:
        execution = _select_run(store, run)
        criterion_id, judge_id, splits = _report_context(execution)
        result = estimate_run(
            store,
            run_id=execution.id,
            criterion_id=criterion_id,
            judge_id=judge_id,
            split_set_id=splits.id,
            rng=np.random.default_rng(seed),
            tag=tag,
            n_boot=n_boot,
        )
        console.print(f"Run {execution.id}; tag={tag or 'all'}; seed={seed}")
        _estimate_table(
            "Judge report card (dev)",
            [
                ("Sensitivity", result.sensitivity),
                ("Specificity", result.specificity),
                ("Cohen kappa", result.kappa),
            ],
        )
        _estimate_table(
            "Representative-case pass rates (test)",
            [
                ("Naive judge", result.naive),
                ("Rogan-Gladen", result.corrected),
                ("PPI", result.ppi),
            ],
        )
        console.print(
            f"Dev cases={result.dev_cases}; calibration pairs={result.calibration_pairs}; "
            f"unresolved labels={result.unresolved_labels}; "
            f"dev UNKNOWN/missing={result.dev_unknown}; missing={result.dev_missing}"
        )
        console.print(
            f"Test cases={result.test_cases}; known={result.naive.n}; "
            f"judge UNKNOWN/missing={result.naive.unknown_rate:.1%}; missing={result.test_missing}"
        )
        for warning in result.warnings:
            console.print(warning)


@app.command("compare")
def compare_command(
    baseline: Annotated[str, typer.Option("--baseline")],
    candidate: Annotated[str, typer.Option("--candidate")],
    db: Annotated[Path, typer.Option("--db")],
    tag: str | None = None,
    seed: int = 0,
    target_effect: float = 0.05,
    n_boot: int = 2000,
) -> None:
    """Paired judge-proxy change; independent-pair planning uses a target effect fraction."""
    with _user_errors(), open_store(db) as store:
        first = _select_run(store, baseline)
        second = _select_run(store, candidate)
        criterion_id, judge_id, splits = _report_context(first)
        other_criterion, other_judge, other_splits = _report_context(second)
        if (criterion_id, judge_id, splits.id) != (other_criterion, other_judge, other_splits.id):
            raise DataError("comparison requires the same criterion, judge and split set")
        result = compare_runs(
            store,
            baseline_id=first.id,
            candidate_id=second.id,
            criterion_id=criterion_id,
            judge_id=judge_id,
            split_set_id=splits.id,
            rng=np.random.default_rng(seed),
            tag=tag,
            target_effect=target_effect,
            n_boot=n_boot,
        )
        _estimate_table(
            "Candidate minus baseline: judge proxy", [("Paired difference", result.difference)]
        )
        console.print(
            f"Decision: {result.decision}; lost={result.lost}; gained={result.gained}; "
            f"unmatched={result.unmatched}; UNKNOWN pairs={result.unknown_pairs}"
        )
        if result.p_value is not None:
            console.print(f"McNemar exact p={result.p_value:.4f}")
        if result.required_total is not None:
            console.print(
                f"Target effect={target_effect:.1%}; required total={result.required_total}; "
                f"additional pairs={result.additional_pairs}"
            )
        for warning in result.warnings:
            console.print(warning)


@app.command("audit")
def audit_command(
    run: Annotated[str, typer.Option("--run")],
    db: Annotated[Path, typer.Option("--db")],
    tag: str | None = None,
) -> None:
    """Show locked pile sizes and outcome-read history without reading outcomes."""
    with _user_errors(), open_store(db) as store:
        execution = _select_run(store, run)
        _, _, splits = _report_context(execution)
        counts = store.split_counts(splits.id, tag=tag)
        table = Table(title=f"Locked splits: {splits.id}")
        table.add_column("Split")
        table.add_column("Examples")
        for pile in Split:
            table.add_row(pile.value, str(counts[pile]))
        console.print(table)
        history = Table(title="Test outcome reads (all runs in this split set)")
        history.add_column("Timestamp")
        history.add_column("Purpose")
        for purpose, at in store.test_reads(splits.id):
            history.add_row(at, purpose)
        console.print(history)