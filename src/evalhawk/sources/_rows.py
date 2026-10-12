"""Shared boundary validation for the recorded-output file formats."""

from pathlib import Path

from pydantic import ValidationError

from evalhawk.core.errors import DataError
from evalhawk.core.models import Example, TargetOutput


def parse_row(
    row: dict[str, object], *, path: Path, number: int
) -> tuple[Example, TargetOutput | None]:
    """Move unknown columns into metadata, then validate strict domain records."""
    if "input" not in row or row["input"] is None or row["input"] == "":
        raise DataError(f"{path}: row {number}, input is missing; supply an input")
    example_fields = {
        key: value
        for key, value in row.items()
        if key in {"input", "reference", "group_id", "tags"}
    }
    output_fields = {
        key: value
        for key, value in row.items()
        if key in {"output", "contexts", "usage", "latency_ms"}
    }
    metadata = row.get("metadata", {})
    if not isinstance(metadata, dict):
        raise DataError(f"{path}: row {number}, metadata must be a JSON object")
    known = {*example_fields, *output_fields, "metadata"}
    example_fields["metadata"] = {
        **metadata,
        **{key: value for key, value in row.items() if key not in known},
    }
    group = example_fields.get("group_id")
    if isinstance(group, int) and not isinstance(group, bool):
        example_fields["group_id"] = str(group)
    try:
        example = Example.model_validate(example_fields)
        output = TargetOutput.model_validate(output_fields) if output_fields else None
    except ValidationError as exc:
        field = ".".join(str(part) for part in exc.errors()[0]["loc"])
        raise DataError(
            f"{path}: row {number}, field {field}: {exc.errors()[0]['msg']}; correct the row"
        ) from exc
    return example, output
