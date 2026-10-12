"""Line-by-line JSON imports with location-aware validation."""

import json
from collections.abc import Iterator
from pathlib import Path

from evalhawk.core.errors import DataError
from evalhawk.core.models import Example, TargetOutput
from evalhawk.sources._rows import parse_row


class JSONLSource:
    """Read one JSON object per nonblank physical line; do not load the whole file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> Iterator[tuple[Example, TargetOutput | None]]:
        """Yield validated rows or raise DataError naming the file and row."""
        try:
            with self.path.open(encoding="utf-8-sig") as stream:
                for number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise DataError(
                            f"{self.path}: row {number}, JSON: {exc.msg}; correct the JSON"
                        ) from exc
                    if not isinstance(row, dict) or any(not isinstance(key, str) for key in row):
                        raise DataError(f"{self.path}: row {number}, JSON must be an object")
                    yield parse_row(row, path=self.path, number=number)
        except (OSError, UnicodeError) as exc:
            raise DataError(f"{self.path}: cannot read UTF-8 data: {exc}; check the file") from exc
