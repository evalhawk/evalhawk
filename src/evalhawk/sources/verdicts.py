"""Streaming recorded judge and human annotations in JSONL or CSV."""

import csv
import json
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError

from evalhawk.core.errors import DataError
from evalhawk.core.models import Criterion, Label, Run, Trace, Verdict
from evalhawk.core.protocols import RecordedObservation
from evalhawk.sources._rows import parse_row


class VerdictSource:
    """CSV structured fields use JSON cells; judge may also be PASS/FAIL/UNKNOWN."""

    def __init__(self, path: Path, *, run: Run, criterion: Criterion, judge_id: str) -> None:
        self.path = path
        self.run = run
        self.criterion = criterion
        self.judge_id = judge_id

    def _rows(self) -> Iterator[tuple[int, dict[str, object]]]:
        try:
            with self.path.open(encoding="utf-8-sig", newline="") as stream:
                if self.path.suffix.lower() == ".csv":
                    reader = csv.DictReader(stream, strict=True)
                    headers = reader.fieldnames
                    if not headers or len(headers) != len(set(headers)):
                        raise DataError(f"{self.path}: row 1, duplicate or missing headers")
                    for raw in reader:
                        if None in raw or any(value is None for value in raw.values()):
                            raise DataError(f"{self.path}: row {reader.line_num}, columns mismatch")
                        row: dict[str, object] = {
                            key: value for key, value in raw.items() if value != ""
                        }
                        if "tags" in row:
                            row["tags"] = str(row["tags"]).split("|")
                        for field in ("contexts", "metadata", "usage", "labels", "repeat_index"):
                            if field in row:
                                try:
                                    row[field] = json.loads(str(row[field]))
                                except json.JSONDecodeError as exc:
                                    raise DataError(
                                        f"{self.path}: row {reader.line_num}, {field} must be JSON"
                                    ) from exc
                        yield reader.line_num, row
                elif self.path.suffix.lower() == ".jsonl":
                    for number, line in enumerate(stream, 1):
                        if not line.strip():
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise DataError(f"{self.path}: row {number}, invalid JSON") from exc
                        if not isinstance(row, dict):
                            raise DataError(f"{self.path}: row {number}, expected JSON object")
                        yield number, row
                else:
                    raise DataError(f"{self.path}: format must be .jsonl or .csv")
        except (OSError, UnicodeError, csv.Error) as exc:
            raise DataError(f"{self.path}: read failed; check UTF-8 and quoting: {exc}") from exc

    def load(self) -> Iterator[RecordedObservation]:
        """Validate annotations at the file boundary with file, row and field errors."""
        for number, row in self._rows():
            judge = row.pop("judge", None)
            labels = row.pop("labels", [])
            repeat = row.pop("repeat_index", 0)
            example, output = parse_row(row, path=self.path, number=number)
            if output is None:
                raise DataError(f"{self.path}: row {number}, output is required")
            if not isinstance(labels, list) or not all(isinstance(item, dict) for item in labels):
                raise DataError(f"{self.path}: row {number}, labels must be an array of objects")
            if not isinstance(repeat, int) or isinstance(repeat, bool):
                raise DataError(f"{self.path}: row {number}, repeat_index must be an integer")
            field = "repeat_index"
            try:
                trace = Trace(
                    **output.model_dump(),
                    example_id=example.id,
                    run_id=self.run.id,
                    repeat_index=repeat,
                )
                field = "judge"
                verdict = Verdict.model_validate(
                    {
                        "trace_id": trace.id,
                        "criterion_id": self.criterion.id,
                        "judge_id": self.judge_id,
                        "outcome": judge,
                    }
                )
                field = "labels"
                parsed = tuple(
                    Label.model_validate(
                        {
                            **item,
                            "trace_id": trace.id,
                            "criterion_id": self.criterion.id,
                        }
                    )
                    for item in labels
                )
            except ValidationError as exc:
                detail = exc.errors()[0]
                raise DataError(
                    f"{self.path}: row {number}, {field}.{detail['loc']}: {detail['msg']}"
                ) from exc
            yield RecordedObservation(example, trace, verdict, parsed)
