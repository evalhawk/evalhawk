"""Helpers shared by CLI commands: console, error handling, run selection, tables."""

from collections.abc import Iterator
from contextlib import contextmanager

import typer
from rich.console import Console
from rich.table import Table

from evalhawk.core.errors import DataError, EvalhawkError
from evalhawk.core.models import Run
from evalhawk.core.protocols import Store
from evalhawk.core.results import Estimate
from evalhawk.core.splits import SplitSet

console = Console(markup=False, highlight=False)


@contextmanager
def user_errors() -> Iterator[None]:
    """Print EvalHawk/user errors as one clear line and exit with code 1."""
    try:
        yield
    except (EvalhawkError, ValueError, OSError) as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(code=1) from exc


def select_run(store: Store, selection: str) -> Run:
    """A run by exact ID, or by version name when exactly one execution has it."""
    exact = store.get_run(selection)
    if exact:
        return exact
    matches = store.find_runs(selection)
    if len(matches) != 1:
        raise DataError(
            f"run {selection!r}: found {len(matches)} executions; supply an exact run ID"
        )
    return matches[0]


def report_context(
    run: Run, *, criterion: str | None = None, judge: str | None = None
) -> tuple[str, str, SplitSet]:
    """(criterion_id, judge_id, splits) for a recorded import or a live evaluation run."""
    config = run.config_snapshot
    if "splits" not in config:
        raise DataError("run has no saved split configuration; select an imported or evaluated run")
    splits = SplitSet.model_validate(config["splits"])
    items = config.get("criteria")
    if isinstance(items, list):
        entries = [item for item in items if isinstance(item, dict)]
        matches = [
            item
            for item in entries
            if (criterion is None or item.get("name") == criterion)
            and (judge is None or item.get("judge") == judge)
        ]
        if len(matches) != 1:
            options = ", ".join(f"{item.get('name')} [{item.get('judge')}]" for item in entries)
            raise DataError(
                f"choose one criterion with --criterion (and --judge if needed); this run has: "
                f"{options}"
            )
        return str(matches[0]["criterion_id"]), str(matches[0]["judge_id"]), splits
    criterion_id, judge_id = config.get("criterion_id"), config.get("judge_id")
    if not isinstance(criterion_id, str) or not isinstance(judge_id, str):
        raise DataError("run has no recorded-import configuration; select an imported execution")
    return criterion_id, judge_id, splits


def estimate_table(title: str, rows: list[tuple[str, Estimate]]) -> None:
    """Print estimates as Metric / Estimate / Interval / Confidence / n / Method."""
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
