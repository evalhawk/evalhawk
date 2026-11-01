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
from evalhawk.cli._shared import console, estimate_table, select_run, user_errors
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


def cascade_command(
    run: Annotated[str, typer.Option("--run")],
    criterion: Annotated[str, typer.Option("--criterion")],
    cheap: Annotated[str, typer.Option("--cheap", help="Judge name of the cheap judge")],
    strong: Annotated[str, typer.Option("--strong", help="Judge name of the strong judge")],
    target_accuracy: Annotated[float, typer.Option(help="Accuracy the cascade must reach")] = 0.9,
    config: ConfigOption = Path("evalhawk.toml"),
    db: DbOption = None,
) -> None:
    """Choose a cheap→strong cascade threshold on dev labels (cost vs accuracy)."""
    from evalhawk.services.cascade import analyse_cascade

    with user_errors(), open_store(database(db, config)) as store:
        execution = select_run(store, run)
        result = analyse_cascade(
            store,
            execution,
            criterion=criterion,
            cheap=cheap,
            strong=strong,
            target_accuracy=target_accuracy,
        )
        curve = result.curve
        table = Table(title=f"Cascade {cheap} -> {strong} on {criterion!r} ({result.n} dev labels)")
        for heading in ("Threshold", "Cheap decides", "Escalations", "Accuracy", "95% interval"):
            table.add_column(heading)
        step = max(1, len(curve.points) // 12)
        shown = list(curve.points[::step])
        if curve.chosen is not None and curve.chosen not in shown:
            shown.append(curve.chosen)
        for point in sorted(shown, key=lambda p: p.threshold):
            mark = "  <- chosen" if point is curve.chosen else ""
            table.add_row(
                f"{point.threshold:.3f}{mark}",
                f"{point.coverage:.0%}",
                str(point.escalations),
                f"{point.accuracy.point:.1%}",
                f"[{point.accuracy.low:.1%}, {point.accuracy.high:.1%}]",
            )
        console.print(table)
        console.print(
            f"Cheap alone: {curve.cheap_accuracy.point:.1%}; strong alone: "
            f"{curve.strong_accuracy.point:.1%}."
        )
        errors = result.errors
        conditional = errors.strong_wrong_given_cheap_wrong
        if conditional is not None:
            console.print(
                f"Strong wrong overall {errors.strong_wrong.point:.1%}; strong wrong when cheap "
                f"is wrong {conditional.point:.1%} [{conditional.low:.1%}, {conditional.high:.1%}]"
                + (f"; lift {errors.lift:.1f}x" if errors.lift is not None else "")
                + ". Near 1x: independent errors, escalation helps; far above: they fail together."
            )
        if result.skipped_no_probability:
            console.print(f"{result.skipped_no_probability} answers skipped: no cheap probability.")
        if curve.chosen is None:
            console.print(
                f"No threshold reaches {target_accuracy:.0%}; use the strong judge alone."
            )
        else:
            console.print(
                f'Add to evalhawk.toml:  [judges.cascade]  type = "cascade"  cheap = "{cheap}"'
                f'  strong = "{strong}"  threshold = {curve.chosen.threshold:.3f}'
            )
            console.print("Chosen on dev: confirm it on test before trusting the cost saving.")


def retrieval_command(
    run: Annotated[str, typer.Option("--run")],
    k: Annotated[int, typer.Option(help="Cut-off rank for @k metrics")] = 5,
    config: ConfigOption = Path("evalhawk.toml"),
    db: DbOption = None,
    seed: int = 0,
    n_boot: int = 2000,
) -> None:
    """RAG retrieval quality (hit@k, recall@k, precision@k, MRR, nDCG@k) with intervals."""
    import numpy as np

    from evalhawk.services.retrieval import run_retrieval

    with user_errors(), open_store(database(db, config)) as store:
        execution = select_run(store, run)
        report = run_retrieval(
            store, execution, k=k, rng=np.random.default_rng(seed), n_boot=n_boot
        )
        s = report.summary
        estimate_table(
            f"Retrieval quality ({report.queries} queries)",
            [
                (f"hit@{k}", s.hit),
                (f"recall@{k}", s.recall),
                (f"precision@{k}", s.precision),
                ("MRR", s.mrr),
                (f"nDCG@{k}", s.ndcg),
            ],
        )
        if report.skipped:
            console.print(f"{report.skipped} answers skipped: no relevant_ids or retrieved_ids.")


NAMING_PROMPT = (
    "These are reasons why answers from an AI assistant failed. They come from one cluster "
    "of similar failures. Propose ONE failure mode they share.\n\n{examples}\n\n"
    "Reply with exactly two lines:\n"
    "NAME: a short snake_case name\n"
    "QUESTION: one yes/no question that is answered 'yes' when an answer does NOT have "
    "this failure"
)


def discover_command(
    run: Annotated[str, typer.Option("--run")],
    criterion: Annotated[str | None, typer.Option(help="Only this criterion's failures")] = None,
    k: Annotated[int | None, typer.Option(help="Number of clusters (default ~sqrt(n/2))")] = None,
    namer: Annotated[
        str | None, typer.Option(help="An LLM judge from evalhawk.toml to propose names")
    ] = None,
    config: ConfigOption = Path("evalhawk.toml"),
    db: DbOption = None,
    seed: int = 0,
) -> None:
    """Cluster failure reasons (judge reasoning, human notes) into candidate criteria."""
    from evalhawk.judges.prompt import PromptJudge
    from evalhawk.services.discover import discover
    from evalhawk.wiring import build_judge

    with user_errors(), open_store(database(db, config)) as store:
        execution = select_run(store, run)
        clusters, texts = discover(store, execution, criterion=criterion, k=k, seed=seed)
        judge = None
        if namer is not None:
            cfg = load_config(config)
            if namer not in cfg.judges:
                raise ConfigError(f"--namer {namer!r} is not a judge in {config}")
            judge = build_judge(namer, cfg.judges[namer], base_dir=cfg.base_dir, others=cfg.judges)
            if not isinstance(judge, PromptJudge):
                raise ConfigError("--namer must be an LLM (openai_compatible) judge")
        console.print(f"{len(texts)} failure reasons in {len(clusters)} clusters (largest first):")
        for number, cluster in enumerate(clusters, 1):
            terms = ", ".join(cluster.top_terms)
            console.print(f"\n[{number}] {cluster.size} reasons; key words: {terms}")
            for example in cluster.examples:
                console.print(f"    - {example[:160]}")
            if judge is not None:
                examples = "\n".join(f"- {e}" for e in cluster.examples)
                messages = [{"role": "user", "content": NAMING_PROMPT.format(examples=examples)}]
                reply = asyncio.run(judge.complete(messages)).text
                console.print("    Proposed criterion (review before adding to evalhawk.toml):")
                for line in reply.strip().splitlines()[:2]:
                    console.print(f"      {line.strip()}")
        console.print(
            "\nTurn a cluster into a criterion by adding it to evalhawk.toml, e.g.\n"
            '  [[criteria]]\n  name = "..."\n  question = "Is the answer free of ...?"'
        )


judges_app.command("status")(status_command)
judges_app.command("cascade")(cascade_command)
judges_app.command("compare")(compare_judges_command)

__all__ = [
    "discover_command",
    "eval_command",
    "export_command",
    "init_command",
    "judges_app",
    "retrieval_command",
    "ui_command",
]
