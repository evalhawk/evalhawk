"""Streaming CSV with UTF-8 BOM support and JSON-valued structured columns."""

import csv
import json
from collections.abc import Iterator
from pathlib import Path

from evalhawk.core.errors import DataError
from evalhawk.core.models import Example, TargetOutput
from evalhawk.sources._rows import parse_row


class CSVSource:
    """Read input/output as text; contexts, metadata and usage use JSON cells."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> Iterator[tuple[Example, TargetOutput | None]]:
        """Yield rows; tags are a pipe-separated list and blanks mean absent values."""
        try:
            with self.path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream, strict=True)
                headers = reader.fieldnames
                if not headers or "input" not in headers or len(headers) != len(set(headers)):
                    raise DataError(
                        f"{self.path}: row 1, input header missing or duplicate headers; "
                        "correct columns"
                    )
                for raw in reader:
                    number = reader.line_num
                    if None in raw or any(value is None for value in raw.values()):
                        raise DataError(f"{self.path}: row {number}, columns do not match header")
                    row: dict[str, object] = {
                        key: value for key, value in raw.items() if value != ""
                    }
                    if "tags" in row:
                        row["tags"] = str(row["tags"]).split("|")
                    for field in ("contexts", "metadata", "usage"):
                        if field in row:
                            try:
                                row[field] = json.loads(str(row[field]))
                            except json.JSONDecodeError as exc:
                                raise DataError(
                                    f"{self.path}: row {number}, {field} must be JSON"
                                ) from exc
                    yield parse_row(row, path=self.path, number=number)
        except (OSError, UnicodeError, csv.Error) as exc:
            raise DataError(
                f"{self.path}: CSV read failed: {exc}; check UTF-8 and quoting"
            ) from exc
