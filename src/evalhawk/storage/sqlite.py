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
        
    def get_split(self, split_set_id: str, example_id: str) -> Split | None:
        """Read an assignment without exposing evaluation outcomes."""
        row = self._connection.execute(
            "SELECT split FROM splits WHERE split_set_id=? AND example_id=?",
            (split_set_id, example_id),
        ).fetchone()
        return Split(row[0]) if row else None

    def get_verdict(self, trace_id: str, criterion_id: str, judge_id: str) -> Verdict | None:
        """Read the cached judge answer without selecting a split."""
        row = self._connection.execute(
            "SELECT record FROM verdicts WHERE trace_id=? AND criterion_id=? AND judge_id=?",
            (trace_id, criterion_id, judge_id),
        ).fetchone()
        return Verdict.model_validate_json(row[0]) if row else None

    def put_verdict(self, verdict: Verdict) -> None:
        """Keep cached judgments immutable; a changed answer requires a new judge ID."""
        with self._transaction():
            previous = self.get_verdict(verdict.trace_id, verdict.criterion_id, verdict.judge_id)
            if previous and (previous.outcome, previous.probability) != (
                verdict.outcome,
                verdict.probability,
            ):
                raise DataError("cached verdict differs; use a new judge_id for changed judgments")
            self._connection.execute(
                "INSERT OR IGNORE INTO verdicts VALUES (?, ?, ?, ?)",
                (verdict.trace_id, verdict.criterion_id, verdict.judge_id, _payload(verdict)),
            )

    def add_label(self, label: Label) -> None:
        """Preserve annotation history rather than silently choosing a human answer."""
        with self._transaction():
            self._connection.execute(
                "INSERT OR IGNORE INTO labels VALUES (?, ?, ?, ?)",
                (label.id, label.trace_id, label.criterion_id, _payload(label)),
            )

    def paired_records(
        self,
        *,
        run_id: str,
        criterion_id: str,
        judge_id: str,
        split_set_id: str,
        split: Split,
        purpose: str,
        tag: str | None = None,
    ) -> Iterator[PairedRecord]:
        """Stream judge/human pairs; multiple annotations remain explicit rows."""
        if not purpose.strip():
            raise DataError("purpose must describe why outcomes are being read")
        if split == Split.TEST:
            with self._transaction():
                self._connection.execute(
                    "INSERT INTO test_access_log(split_set_id,purpose,at) VALUES (?,?,?)",
                    (split_set_id, purpose, datetime.now(UTC).isoformat()),
                )
        cursor = self._connection.execute(
            "SELECT t.example_id,s.group_id,t.id,v.record,l.record FROM traces t "
            "JOIN splits s ON s.example_id=t.example_id "
            "JOIN verdicts v ON v.trace_id=t.id AND v.criterion_id=? AND v.judge_id=? "
            "LEFT JOIN labels l ON l.trace_id=t.id AND l.criterion_id=v.criterion_id "
            "WHERE t.run_id=? AND s.split_set_id=? AND s.split=? "
            "AND (? IS NULL OR EXISTS (SELECT 1 FROM example_tags et "
            "WHERE et.example_id=t.example_id AND et.tag=?)) "
            "ORDER BY t.example_id,t.repeat_index,l.id",
            (criterion_id, judge_id, run_id, split_set_id, split.value, tag, tag),
        )
        try:
            for example_id, group_id, trace_id, verdict_json, label_json in cursor:
                verdict = Verdict.model_validate_json(verdict_json)
                label = Label.model_validate_json(label_json) if label_json else None
                yield PairedRecord(
                    example_id,
                    group_id,
                    trace_id,
                    verdict.outcome,
                    label.outcome if label else None,
                    label.annotator if label else None,
                    label.inclusion_prob if label else None,
                )
        finally:
            cursor.close()

    def split_counts(self, split_set_id: str, *, tag: str | None = None) -> dict[Split, int]:
        """Return actual per-tag pile sizes without reading outcomes."""
        counts = dict.fromkeys(Split, 0)
        for pile, count in self._connection.execute(
            "SELECT split,count(*) FROM splits s WHERE split_set_id=? "
            "AND (? IS NULL OR EXISTS(SELECT 1 FROM example_tags et "
            "WHERE et.example_id=s.example_id AND et.tag=?)) GROUP BY split",
            (split_set_id, tag, tag),
        ):
            counts[Split(pile)] = count
        return counts

    def close(self) -> None:
        """Release the connection before removing or moving a database file."""
        self._connection.close()

    def find_runs(self, target_version: str) -> list[Run]:
        """Find executions by version; callers must refuse ambiguous selections."""
        return [
            run
            for (payload,) in self._connection.execute("SELECT record FROM runs ORDER BY id")
            if (run := Run.model_validate_json(payload)).target_version == target_version
        ]

    def test_reads(self, split_set_id: str) -> list[tuple[str, str]]:
        """Return purpose and UTC timestamp for every audited test read."""
        return list(
            self._connection.execute(
                "SELECT purpose,at FROM test_access_log WHERE split_set_id=? ORDER BY id",
                (split_set_id,),
            )
        )

    def get_run(self, run_id: str) -> Run | None:
        """Read one execution by its content ID."""
        row = self._connection.execute("SELECT record FROM runs WHERE id=?", (run_id,)).fetchone()
        return Run.model_validate_json(row[0]) if row else None

    def outcome_rows(
        self,
        *,
        run_id: str,
        criterion_id: str,
        judge_id: str,
        split_set_id: str,
        split: Split,
        purpose: str,
        tag: str | None = None,
        include_labels: bool = True,
    ) -> Iterator[OutcomeRow]:
        """Stream indexed identifiers and generated scalar outcomes, never full JSON."""
        if not purpose.strip():
            raise DataError("purpose must describe why outcomes are being read")
        if split == Split.TEST:
            with self._transaction():
                self._connection.execute(
                    "INSERT INTO test_access_log(split_set_id,purpose,at) VALUES (?,?,?)",
                    (split_set_id, purpose, datetime.now(UTC).isoformat()),
                )
        cursor = self._connection.execute(
            "SELECT t.example_id,s.group_id,t.id,t.repeat_index,v.outcome,"
            "l.outcome,l.annotator,l.inclusion_prob,l.created_at FROM traces t "
            "JOIN splits s ON s.example_id=t.example_id "
            "LEFT JOIN verdicts v ON v.trace_id=t.id AND v.criterion_id=? AND v.judge_id=? "
            "LEFT JOIN labels l ON l.trace_id=t.id AND l.criterion_id=? AND ? "
            "WHERE t.run_id=? AND s.split_set_id=? AND s.split=? "
            "AND (? IS NULL OR EXISTS (SELECT 1 FROM example_tags et "
            "WHERE et.example_id=t.example_id AND et.tag=?)) "
            "ORDER BY t.example_id,t.repeat_index,l.id",
            (
                criterion_id,
                judge_id,
                criterion_id,
                include_labels,
                run_id,
                split_set_id,
                split.value,
                tag,
                tag,
            ),
        )
        try:
            for example, group, trace, repeat, judge, human, annotator, probability, at in cursor:
                yield OutcomeRow(
                    example,
                    group,
                    trace,
                    repeat,
                    Outcome(judge) if judge else Outcome.UNKNOWN,
                    Outcome(human) if human else None,
                    annotator,
                    probability,
                    datetime.fromisoformat(at) if at else None,
                    judge is None,
                )
        finally:
            cursor.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
