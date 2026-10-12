"""SQLite state store with atomic batches, immutable splits and audited test reads."""

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from itertools import islice
from pathlib import Path
from typing import Self

from evalhawk.core.errors import DataError, StoreError
from evalhawk.core.models import (
    Criterion,
    Example,
    Label,
    Outcome,
    Record,
    Run,
    Split,
    Trace,
    Verdict,
)
from evalhawk.core.protocols import OutcomeRow, PairedRecord
from evalhawk.core.splits import SplitSet, split_key


def _payload(record: Record) -> str:
    payload = record.model_dump_json()
    type(record).model_validate_json(payload)
    return payload


class SQLiteStore:
    """Use on one thread; async callers must delegate complete operations to a worker."""

    def __init__(self, path: str | Path, *, busy_timeout: int = 5000) -> None:
        if busy_timeout < 0:
            raise ValueError("busy_timeout must be non-negative")
        try:
            self._connection = sqlite3.connect(str(path), isolation_level=None)
        except sqlite3.Error as exc:
            raise StoreError(f"cannot open SQLite store at {path}; check path and access") from exc
        try:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.execute("PRAGMA recursive_triggers=ON")
            self._connection.execute(f"PRAGMA busy_timeout={int(busy_timeout)}")
            with self._transaction():
                version = self._connection.execute("PRAGMA user_version").fetchone()[0]
                if version > 2:
                    raise StoreError("database schema is newer than this package; upgrade evalhawk")
                for migration_version, migration in (
                    (1, "0001_init.sql"),
                    (2, "0002_outcome_columns.sql"),
                ):
                    if version >= migration_version:
                        continue
                    script = (
                        files("evalhawk.storage")
                        .joinpath(f"migrations/{migration}")
                        .read_text(encoding="utf-8")
                    )
                    statement = ""
                    for line in script.splitlines(keepends=True):
                        statement += line
                        if sqlite3.complete_statement(statement):
                            self._connection.execute(statement)
                            statement = ""
                    if statement.strip():
                        raise StoreError(
                            "incomplete migration SQL; repair the package installation"
                        )
                    self._connection.execute(f"PRAGMA user_version={migration_version}")
        except sqlite3.Error as exc:
            self._connection.close()
            raise StoreError(f"cannot initialize SQLite store at {path}; check access") from exc
        except StoreError:
            self._connection.close()
            raise

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._connection.rollback()
                raise
            self._connection.commit()
        except sqlite3.Error as exc:
            raise StoreError(
                f"SQLite operation failed: {exc}; check references and database access"
            ) from exc

    def add_examples(self, examples: Iterable[Example]) -> None:
        """Upsert descriptive metadata/tags; split rows retain their own grouping snapshot."""
        with self._transaction():
            iterator = iter(examples)
            while batch := tuple(islice(iterator, 500)):
                records = {example.id: (example, _payload(example)) for example in batch}
                self._connection.executemany(
                    "INSERT INTO examples VALUES (?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET record=excluded.record",
                    ((example_id, record[1]) for example_id, record in records.items()),
                )
                placeholders = ",".join("?" for _ in records)
                self._connection.execute(
                    f"DELETE FROM example_tags WHERE example_id IN ({placeholders})",
                    tuple(records),
                )
                self._connection.executemany(
                    "INSERT OR IGNORE INTO example_tags VALUES (?, ?)",
                    ((example.id, tag) for example, _ in records.values() for tag in example.tags),
                )

    def add_run(self, run: Run) -> None:
        """Persist a run, retaining the first stored execution metadata."""
        with self._transaction():
            self._connection.execute(
                "INSERT OR IGNORE INTO runs VALUES (?, ?)", (run.id, _payload(run))
            )

    def add_traces(self, run: Run, traces: Iterable[Trace]) -> None:
        """Atomically insert a run and traces; conflicting repeat slots are errors."""
        with self._transaction():
            self._connection.execute(
                "INSERT OR IGNORE INTO runs VALUES (?, ?)", (run.id, _payload(run))
            )
            for trace in traces:
                if trace.run_id != run.id:
                    raise DataError(
                        "trace run_id differs from supplied run; supply the matching run"
                    )
                payload = _payload(trace)
                previous = self._connection.execute(
                    "SELECT id FROM traces WHERE example_id=? AND run_id=? AND repeat_index=?",
                    (trace.example_id, run.id, trace.repeat_index),
                ).fetchone()
                if previous and previous[0] != trace.id:
                    raise DataError(
                        "trace repeat slot already contains another output; "
                        "use a new run or repeat_index"
                    )
                self._connection.execute(
                    "INSERT OR IGNORE INTO traces VALUES (?, ?, ?, ?, ?)",
                    (trace.id, trace.example_id, run.id, trace.repeat_index, payload),
                )

    def add_criterion(self, criterion: Criterion) -> None:
        """Persist a versioned binary criterion."""
        with self._transaction():
            self._connection.execute(
                "INSERT OR IGNORE INTO criteria VALUES (?, ?)", (criterion.id, _payload(criterion))
            )

    def assign_splits(self, config: SplitSet, examples: Iterable[Example]) -> None:
        """Lock assignments and reject config/group changes within the same set."""
        with self._transaction():
            existing = self._connection.execute(
                "SELECT id FROM split_sets WHERE salt=?", (config.salt,)
            ).fetchone()
            if existing and existing[0] != config.id:
                raise DataError("salt already identifies different ratios/by; choose a new salt")
            self._connection.execute(
                "INSERT OR IGNORE INTO split_sets VALUES (?, ?, ?)",
                (config.id, config.salt, _payload(config)),
            )
            for example in examples:
                _payload(example)
                key = split_key(example, by=config.by)
                previous = self._connection.execute(
                    "SELECT split_key FROM splits WHERE split_set_id=? AND example_id=?",
                    (config.id, example.id),
                ).fetchone()
                if previous and previous[0] != key:
                    raise DataError(
                        "group changed in a locked split set; "
                        "create a new salt and record prior exposure"
                    )
                self._connection.execute(
                    "INSERT OR IGNORE INTO splits VALUES (?, ?, ?, ?, ?)",
                    (config.id, example.id, key, example.group_id, config.assign(example).value),
                )

