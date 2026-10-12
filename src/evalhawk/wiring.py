"""Construct concrete adapters at the application boundary."""

from pathlib import Path

from evalhawk.core.models import Criterion, Run
from evalhawk.sources.verdicts import VerdictSource
from evalhawk.storage.sqlite import SQLiteStore


def open_store(path: Path) -> SQLiteStore:
    """Open the user's explicitly selected evaluation database."""
    return SQLiteStore(path)


def recorded_source(path: Path, *, run: Run, criterion: Criterion, judge_id: str) -> VerdictSource:
    """Create a file adapter without exposing it to services."""
    return VerdictSource(path, run=run, criterion=criterion, judge_id=judge_id)