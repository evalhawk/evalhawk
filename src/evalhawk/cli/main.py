"""Entry point for the ``evalhawk`` command."""

from pathlib import Path
from typing import Annotated

import numpy as np
import typer
from rich.table import Table

from evalhawk import __version__
from evalhawk.cli import live
from evalhawk.cli._shared import console, estimate_table, report_context, select_run, user_errors
from evalhawk.core.errors import DataError, EvalhawkError
from evalhawk.core.models import Criterion, Run, Split
from evalhawk.core.protocols import Store
from evalhawk.core.splits import SplitSet
from evalhawk.services.compare import CorrectedComparison, corrected_compare
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


demo = typer.Typer(help="Generate an offline synthetic evaluation.", no_args_is_help=True)
app.add_typer(demo, name="demo")
app.command("init")(live.init_command)
app.command("eval")(live.eval_command)
app.command("export")(live.export_command)
app.command("ui")(live.ui_command)
app.command("retrieval")(live.retrieval_command)
app.add_typer(live.judges_app, name="judges")

# Backwards-compatible names for the helpers that moved to cli/_shared.py.
_user_errors = user_errors
_select_run = select_run
_report_context = report_context
_estimate_table = estimate_table


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
    criterion: Annotated[str | None, typer.Option(help="Criterion name (evaluated runs)")] = None,
    judge: Annotated[
        str | None, typer.Option(help="Judge name, if a criterion has several")
    ] = None,
) -> None:
    """Judge report card and representative-case rates with confidence intervals."""
    with _user_errors(), open_store(db) as store:
        execution = _select_run(store, run)
        criterion_id, judge_id, splits = _report_context(
            execution, criterion=criterion, judge=judge
        )
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
    criterion: Annotated[str | None, typer.Option(help="Criterion name (evaluated runs)")] = None,
    judge: Annotated[
        str | None, typer.Option(help="Judge name, if a criterion has several")
    ] = None,
    corrected: Annotated[
        bool, typer.Option(help="Correct for the judge's errors using dev human labels")
    ] = False,
) -> None:
    """Paired v2-v1 change; --corrected removes the judge's bias using human labels."""
    if corrected:
        with _user_errors(), open_store(db) as store:
            result = _corrected(store, baseline, candidate, criterion, judge, tag, seed, n_boot)
            _print_corrected(result)
        return
    with _user_errors(), open_store(db) as store:
        first = _select_run(store, baseline)
        second = _select_run(store, candidate)
        criterion_id, judge_id, splits = _report_context(first, criterion=criterion, judge=judge)
        other_criterion, other_judge, other_splits = _report_context(
            second, criterion=criterion, judge=judge
        )
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
        splits = SplitSet.model_validate(execution.config_snapshot["splits"])
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


def _corrected(
    store: Store,
    baseline: str,
    candidate: str,
    criterion: str | None,
    judge: str | None,
    tag: str | None,
    seed: int,
    n_boot: int,
) -> CorrectedComparison:
    first = select_run(store, baseline)
    second = select_run(store, candidate)
    criterion_id, judge_id, splits = report_context(first, criterion=criterion, judge=judge)
    other = report_context(second, criterion=criterion, judge=judge)
    if (criterion_id, judge_id, splits.id) != (other[0], other[1], other[2].id):
        raise DataError("comparison requires the same criterion, judge and split set")
    return corrected_compare(
        store,
        baseline_id=first.id,
        candidate_id=second.id,
        criterion_id=criterion_id,
        judge_id=judge_id,
        split_set_id=splits.id,
        rng=np.random.default_rng(seed),
        tag=tag,
        n_boot=n_boot,
    )


def _print_corrected(result: CorrectedComparison) -> None:
    estimate_table(
        "Candidate minus baseline",
        [("Judged (uncorrected)", result.proxy), ("Corrected for the judge", result.difference)],
    )
    console.print(
        f"Decision: {result.decision}; calibration labels={result.calibration_pairs}; "
        f"unmatched={result.unmatched}; UNKNOWN pairs={result.unknown_pairs}"
    )
    for warning in result.warnings:
        console.print(warning)


@app.command("gate")
def gate_command(
    baseline: Annotated[str, typer.Option("--baseline")],
    candidate: Annotated[str, typer.Option("--candidate")],
    db: Annotated[Path, typer.Option("--db")],
    criterion: Annotated[str | None, typer.Option(help="Criterion name")] = None,
    judge: Annotated[str | None, typer.Option(help="Judge name")] = None,
    corrected: Annotated[bool, typer.Option(help="Use the bias-corrected difference")] = False,
    fail_on: Annotated[
        str, typer.Option(help="'worse' (default) or 'inconclusive' to also fail when unsure")
    ] = "worse",
    tag: str | None = None,
    seed: int = 0,
    n_boot: int = 2000,
) -> None:
    """CI gate. Exit 0 = OK, 1 = significant regression, 2 = error (bad config, no data...)."""
    if fail_on not in {"worse", "inconclusive"}:
        console.print("Error: --fail-on must be 'worse' or 'inconclusive'")
        raise typer.Exit(code=2)
    try:
        with open_store(db) as store:
            if corrected:
                result = _corrected(store, baseline, candidate, criterion, judge, tag, seed, n_boot)
                _print_corrected(result)
                decision = result.decision
            else:
                first, second = select_run(store, baseline), select_run(store, candidate)
                criterion_id, judge_id, splits = report_context(
                    first, criterion=criterion, judge=judge
                )
                proxy = compare_runs(
                    store,
                    baseline_id=first.id,
                    candidate_id=second.id,
                    criterion_id=criterion_id,
                    judge_id=judge_id,
                    split_set_id=splits.id,
                    rng=np.random.default_rng(seed),
                    tag=tag,
                    n_boot=n_boot,
                )
                estimate_table(
                    "Candidate minus baseline: judge proxy",
                    [("Paired difference", proxy.difference)],
                )
                decision = proxy.decision
    except (EvalhawkError, ValueError, OSError) as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(code=2) from exc
    failed = decision == "WORSE" or (fail_on == "inconclusive" and decision == "INCONCLUSIVE")
    console.print(f"GATE {'FAILED' if failed else 'PASSED'}: {decision}")
    raise typer.Exit(code=1 if failed else 0)
