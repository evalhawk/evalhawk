"""Live-evaluation commands: init, eval, judges status/compare, export."""

import asyncio
import csv
import getpass
import json
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from evalhawk.cli import templates
from evalhawk.cli._shared import console, select_run, user_errors
from evalhawk.config import CODE_JUDGE, Config, load_config
from evalhawk.core.errors import ConfigError, DataError
from evalhawk.core.splits import SplitSet
from evalhawk.runner.executor import RunnerSettings
from evalhawk.services.calibrate import calibration_status
from evalhawk.services.evaluate import (
    find_or_create_run,
    judged_rates,
    run_evaluation,
    run_snapshot,
    sample_examples,
)
from evalhawk.services.export import export_rows
from evalhawk.wiring import build_specs, build_target, load_rows, needs_reference, open_store

judges_app = typer.Typer(help="Inspect and compare judges.", no_args_is_help=True)

ConfigOption = Annotated[Path, typer.Option("--config", "-c", help="Path to evalhawk.toml")]
DbOption = Annotated[
    Path | None, typer.Option("--db", help="Database (default: [project].store in the config)")
]


def database(db: Path | None, config: Path) -> Path:
    """The ``--db`` path, or the store named in the config."""
    if db is not None:
        return db
    loaded = load_config(config)
    return loaded.resolve(loaded.project.store)


def splits_of(config: Config) -> SplitSet:
    return SplitSet(salt=config.splits.salt, ratios=config.splits.ratios, by=config.splits.by)


def init_command(
    directory: Annotated[Path, typer.Argument(help="Folder to create the project in")] = Path("."),
    force: bool = False,
) -> None:
    """Create a runnable quickstart: evalhawk.toml, app.py and data/questions.jsonl."""
    with user_errors():
        files = {
            directory / "evalhawk.toml": templates.CONFIG,
            directory / "app.py": templates.APP,
            directory / "data" / "questions.jsonl": templates.QUESTIONS,
        }
        existing = [path for path in files if path.exists()]
        if existing and not force:
            raise ConfigError(
                f"{', '.join(map(str, existing))} already exist; use --force to overwrite"
            )
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
            console.print(f"Created {path}")
        console.print("Next: cd into the folder and run `evalhawk eval --target-version v1`")


def eval_command(
    target_version: Annotated[
        str, typer.Option("--target-version", "-t", help="A label for this version of your app")
    ],
    config: ConfigOption = Path("evalhawk.toml"),
    evaluation: Annotated[str | None, typer.Option(help="Which [evaluations.<name>]")] = None,
    sample: Annotated[int | None, typer.Option(help="Evaluate a reproducible subset")] = None,
    fresh: Annotated[bool, typer.Option(help="Start a new run instead of resuming")] = False,
    db: DbOption = None,
) -> None:
    """Run your app on the dataset, judge every answer, and show the judged pass rates."""
    with user_errors():
        cfg = load_config(config)
        name, chosen = cfg.evaluation(evaluation)
        if cfg.target is None:
            raise ConfigError(f"{config}: add a [target] section (how to call your app)")
        rows = load_rows(cfg.resolve(chosen.dataset))
        examples = [example for example, _ in rows]
        if not examples:
            raise DataError(f"{chosen.dataset}: the dataset is empty")
        missing_reference = needs_reference(cfg, name)
        if missing_reference and any(example.reference is None for example in examples):
            count = sum(example.reference is None for example in examples)
            raise DataError(
                f"criteria {', '.join(missing_reference)} need a reference answer, but "
                f"{count} example(s) in {chosen.dataset} have none; add 'reference' to each row"
            )
        examples = sample_examples(examples, sample, seed=cfg.runner.seed)
        target = build_target(cfg.target, base_dir=cfg.base_dir, rows=rows)
        specs, needs_contexts = build_specs(cfg, name)
        splits = splits_of(cfg)
        snapshot = run_snapshot(
            evaluation=name,
            specs=specs,
            judge_names=[judge for _, judge in chosen.pairs()],
            splits=splits,
            repeats=chosen.repeats,
            kind=chosen.kind,
            target=cfg.target.model_dump(mode="json"),
        )
        settings = RunnerSettings(**cfg.runner.model_dump())
        with open_store(database(db, config)) as store:
            run, resumed = find_or_create_run(
                store, target_version=target_version, snapshot=snapshot, fresh=fresh
            )
            console.print(
                f"{'Resuming' if resumed else 'Starting'} run {run.id[:12]} "
                f"({name}, version {target_version}, {len(examples)} examples x "
                f"{chosen.repeats} repeat(s), {len(specs)} criteria)"
            )
            summary = asyncio.run(
                run_evaluation(
                    store,
                    run=run,
                    examples=examples,
                    target=target,
                    specs=specs,
                    splits=splits,
                    repeats=chosen.repeats,
                    settings=settings,
                    require_contexts=needs_contexts,
                )
            )
            work = Table(title="Run summary")
            for heading in (
                "Answers new",
                "Answers reused",
                "Judged now",
                "From cache",
                "Already judged",
                "Cost (USD)",
                "Failures",
            ):
                work.add_column(heading)
            work.add_row(
                str(summary.traces_new),
                str(summary.traces_reused),
                str(summary.verdicts_new),
                str(summary.verdicts_cached),
                str(summary.verdicts_existing),
                f"{summary.cost_usd:.4f}",
                str(len(summary.failures)),
            )
            console.print(work)
            for failure in summary.failures[:5]:
                where = f"{failure.stage} {failure.criterion or ''}".strip()
                console.print(
                    f"  failed: {where} example {failure.example_id[:10]} "
                    f"after {failure.attempts} attempt(s): {failure.error}"
                )
            if summary.budget_stopped:
                console.print(
                    f"Budget reached: {summary.skipped_for_budget} judgment(s) not started. "
                    "Raise [runner].max_cost_usd and rerun to resume."
                )
            rates = Table(title="Judged pass rates (uncorrected, all piles)")
            for heading in ("Criterion", "Judge", "Pass rate", "95% interval", "n", "UNKNOWN"):
                rates.add_column(heading)
            for rate in judged_rates(store, run, splits.id):
                if rate.rate is None:
                    rates.add_row(rate.criterion, rate.judge, "-", "-", "0", str(rate.unknown))
                    continue
                rates.add_row(
                    rate.criterion,
                    rate.judge,
                    f"{rate.rate.point:.1%}",
                    f"[{rate.rate.low:.1%}, {rate.rate.high:.1%}]",
                    str(rate.rate.n),
                    f"{rate.rate.unknown_rate:.0%}",
                )
            console.print(rates)
            llm_judged = [
                s for s in calibration_status(store, run, splits.id) if s.judge != CODE_JUDGE
            ]
            for status in llm_judged:
                if status.status == "ok":
                    console.print(
                        f"{status.criterion} [{status.judge}]: calibrated "
                        f"({status.n_pass} PASS / {status.n_fail} FAIL human labels); "
                        f"corrected numbers: evalhawk report --run {run.id[:12]} "
                        f"--criterion {status.criterion}"
                    )
                else:
                    console.print(
                        f"{status.criterion} [{status.judge}]: not calibrated yet; label about "
                        f"{status.need_more} more answers (evalhawk ui) to get corrected numbers"
                    )
            console.print(f"Run ID: {run.id}")


def status_command(
    run: Annotated[str, typer.Option("--run")],
    config: ConfigOption = Path("evalhawk.toml"),
    db: DbOption = None,
) -> None:
    """Each judge's report card on human-labelled dev answers, and whether it's ready."""
    with user_errors(), open_store(database(db, config)) as store:
        execution = select_run(store, run)
        splits = SplitSet.model_validate(execution.config_snapshot["splits"])
        table = Table(title=f"Judge status for run {execution.id[:12]}")
        for heading in ("Criterion", "Judge", "Sensitivity", "Specificity", "Labels P/F", "Status"):
            table.add_column(heading)
        for status in calibration_status(store, execution, splits.id):
            if status.judge == CODE_JUDGE:
                table.add_row(
                    status.criterion, "code", "-", "-", "-", "exact (no calibration needed)"
                )
                continue
            sens = (
                f"{status.sensitivity.point:.0%} [{status.sensitivity.low:.0%}, "
                f"{status.sensitivity.high:.0%}]"
                if status.sensitivity
                else "-"
            )
            spec = (
                f"{status.specificity.point:.0%} [{status.specificity.low:.0%}, "
                f"{status.specificity.high:.0%}]"
                if status.specificity
                else "-"
            )
            label = (
                "ok" if status.status == "ok" else f"insufficient (need ~{status.need_more} more)"
            )
            table.add_row(
                status.criterion,
                status.judge,
                sens,
                spec,
                f"{status.n_pass}/{status.n_fail}",
                label,
            )
        console.print(table)


def compare_judges_command(
    criterion: Annotated[str, typer.Option("--criterion")],
    run: Annotated[list[str], typer.Option("--run", help="Repeat for each run to compare")],
    config: ConfigOption = Path("evalhawk.toml"),
    db: DbOption = None,
) -> None:
    """Side-by-side report cards for every judge of one criterion, across runs."""
    with user_errors(), open_store(database(db, config)) as store:
        table = Table(title=f"Judges compared on {criterion!r} (dev human labels)")
        for heading in ("Run", "Judge", "Sensitivity", "Specificity", "Labels P/F", "Status"):
            table.add_column(heading)
        found = 0
        for selection in run:
            execution = select_run(store, selection)
            splits = SplitSet.model_validate(execution.config_snapshot["splits"])
            for status in calibration_status(store, execution, splits.id):
                if status.criterion != criterion:
                    continue
                found += 1
                fmt = lambda e: f"{e.point:.0%} [{e.low:.0%}, {e.high:.0%}]" if e else "-"  # noqa: E731
                table.add_row(
                    execution.id[:12],
                    status.judge,
                    fmt(status.sensitivity),
                    fmt(status.specificity),
                    f"{status.n_pass}/{status.n_fail}",
                    status.status,
                )
        if not found:
            raise DataError(f"no judge for criterion {criterion!r} in the selected run(s)")
        console.print(table)


def export_command(
    run: Annotated[str, typer.Option("--run")],
    out: Annotated[Path, typer.Option("--out", help="Output file: .jsonl or .csv")],
    config: ConfigOption = Path("evalhawk.toml"),
    db: DbOption = None,
) -> None:
    """Write every answer with its verdicts and human labels to JSONL or CSV."""
    with user_errors(), open_store(database(db, config)) as store:
        execution = select_run(store, run)
        splits = SplitSet.model_validate(execution.config_snapshot["splits"])
        rows = list(export_rows(store, execution.id, splits.id))
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix.lower() == ".jsonl":
            with out.open("w", encoding="utf-8", newline="\n") as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        elif out.suffix.lower() == ".csv":
            columns = sorted({key for row in rows for key in row}, key=lambda k: (k.count("."), k))
            with out.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                for row in rows:
                    writer.writerow(
                        {
                            k: json.dumps(v, ensure_ascii=False)
                            if isinstance(v, dict | list)
                            else v
                            for k, v in row.items()
                        }
                    )
        else:
            raise DataError("--out must end in .jsonl or .csv")
        console.print(f"Exported {len(rows)} answers to {out} (test-pile read logged as 'export').")


def ui_command(
    config: ConfigOption = Path("evalhawk.toml"),
    db: DbOption = None,
    annotator: Annotated[
        str | None, typer.Option(help="Your name on saved labels (default: your login)")
    ] = None,
    host: Annotated[str, typer.Option(help="Interface to bind; keep 127.0.0.1")] = "127.0.0.1",
    port: int = 8765,
    seed: int = 0,
) -> None:
    """Open the local web app: runs, blind labelling and judge report cards."""
    with user_errors():
        try:
            import uvicorn

            from evalhawk.ui.app import create_app
        except ImportError as exc:
            raise ConfigError(
                f'the web UI needs the [ui] extra: pip install "evalhawk[ui]" ({exc.name} missing)'
            ) from exc
        name = annotator or getpass.getuser()
        path = database(db, config)
        if host not in {"127.0.0.1", "localhost", "::1"}:
            console.print(f"Warning: binding to {host} exposes your labels to the network.")
        console.print(f"EvalHawk UI: http://{host}:{port}  (labelling as {name}; Ctrl+C to stop)")
        uvicorn.run(
            create_app(path, annotator=name, seed=seed), host=host, port=port, log_level="warning"
        )


judges_app.command("status")(status_command)
judges_app.command("compare")(compare_judges_command)

__all__ = ["eval_command", "export_command", "init_command", "judges_app", "ui_command"]
