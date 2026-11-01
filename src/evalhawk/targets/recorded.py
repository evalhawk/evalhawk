"""Replay outputs that already exist (no calls to the application)."""

from collections.abc import Iterable, Mapping

from evalhawk.core.errors import DataError
from evalhawk.core.models import Example, TargetOutput


class RecordedTarget:
    """Return stored outputs by example ID, e.g. from a JSONL file with an ``output`` column."""

    def __init__(self, outputs: Mapping[str, TargetOutput]) -> None:
        self.outputs = dict(outputs)

    @classmethod
    def from_rows(cls, rows: Iterable[tuple[Example, TargetOutput | None]]) -> "RecordedTarget":
        """Build from a TraceSource's rows; rows without an output are rejected."""
        outputs: dict[str, TargetOutput] = {}
        for example, output in rows:
            if output is None:
                raise DataError(f"example {example.id}: no recorded output to replay")
            outputs[example.id] = output
        return cls(outputs)

    async def __call__(self, example: Example) -> TargetOutput:
        try:
            return self.outputs[example.id]
        except KeyError:
            raise DataError(f"no recorded output for example {example.id}") from None
