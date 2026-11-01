"""Code-check metrics: deterministic judges that need no model call.

They are exact and free, so they need no human calibration, but they still get error
ranges and version comparison like every other criterion. Each check returns PASS or
FAIL, or UNKNOWN when the data it needs is missing (for example, no reference answer).
"""

import json
import re
import string
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from evalhawk.core.ids import content_id
from evalhawk.core.models import Criterion, Example, Outcome, Trace, Verdict

CheckResult = tuple[Outcome, str]
CheckFunction = Callable[[Example, Trace, Mapping[str, Any]], CheckResult]

_PII = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"(?<!\d)(?:\+?\d[\s().-]?){9,14}\d(?!\d)"),
    "card_number": re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
}


def _normalise(text: str, steps: Sequence[str]) -> str:
    if "case" in steps:
        text = text.casefold()
    if "punctuation" in steps:
        text = text.translate(str.maketrans("", "", string.punctuation))
    if "whitespace" in steps:
        text = " ".join(text.split())
    return text


def _result(ok: bool, passed: str, failed: str) -> CheckResult:
    return (Outcome.PASS, passed) if ok else (Outcome.FAIL, failed)


def _reference_text(example: Example) -> str | None:
    return example.reference if isinstance(example.reference, str) else None


def _exact_match(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    reference = _reference_text(example)
    if reference is None:
        return Outcome.UNKNOWN, "no text reference answer to compare with"
    steps = options.get("normalise", ["whitespace"])
    ok = _normalise(trace.output, steps) == _normalise(reference, steps)
    return _result(ok, "output matches the reference", "output differs from the reference")


def _contains(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    value = str(options["value"])
    haystack, needle = trace.output, value
    if not options.get("case_sensitive", False):
        haystack, needle = haystack.casefold(), needle.casefold()
    return _result(needle in haystack, f"contains {value!r}", f"does not contain {value!r}")


def _not_contains(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    outcome, _ = _contains(example, trace, options)
    value = options["value"]
    return _result(outcome is Outcome.FAIL, f"does not contain {value!r}", f"contains {value!r}")


def _regex(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    pattern = re.compile(str(options["pattern"]))
    return _result(
        pattern.search(trace.output) is not None,
        f"matches /{pattern.pattern}/",
        f"does not match /{pattern.pattern}/",
    )


def _max_words(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    count, limit = len(trace.output.split()), int(options["value"])
    return _result(count <= limit, f"{count} words (limit {limit})", f"{count} words, over {limit}")


def _min_words(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    count, limit = len(trace.output.split()), int(options["value"])
    return _result(count >= limit, f"{count} words (min {limit})", f"{count} words, under {limit}")


def _max_chars(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    count, limit = len(trace.output), int(options["value"])
    return _result(count <= limit, f"{count} characters", f"{count} characters, over {limit}")


def _not_empty(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    return _result(bool(trace.output.strip()), "output is not empty", "output is empty")


def _one_of(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    steps = options.get("normalise", ["case", "whitespace"])
    allowed = {_normalise(str(value), steps) for value in options["values"]}
    value = _normalise(trace.output, steps)
    return _result(value in allowed, f"{value!r} is allowed", f"{value!r} is not an allowed value")


def _parse_json(text: str) -> tuple[bool, Any]:
    try:
        return True, json.loads(text)
    except json.JSONDecodeError:
        return False, None


def _valid_json(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    ok, _ = _parse_json(trace.output)
    return _result(ok, "output is valid JSON", "output is not valid JSON")


_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def schema_errors(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    """Validate a subset of JSON Schema: type, enum, required, properties,
    additionalProperties (False), items, minimum/maximum, minLength/maxLength."""
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        names = expected if isinstance(expected, list) else [expected]
        types = tuple(t for name in names for t in _JSON_TYPES[str(name)])
        is_bool = isinstance(value, bool)
        if not isinstance(value, types) or (is_bool and "boolean" not in names):
            return [f"{path}: expected {expected}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required field {key!r}")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                errors.extend(schema_errors(item, properties[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected field {key!r}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            errors.extend(schema_errors(item, schema["items"], f"{path}[{index}]"))
    if isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} is below the minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} is above the maximum {schema['maximum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']} characters")
    return errors


def _json_schema(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    ok, value = _parse_json(trace.output)
    if not ok:
        return Outcome.FAIL, "output is not valid JSON"
    errors = schema_errors(value, options["schema"])
    return _result(not errors, "output matches the schema", "; ".join(errors[:3]))


def _dig(value: Any, dotted: str) -> tuple[bool, Any]:
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _field_match(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    field = str(options["field"])
    reference: Any = example.reference
    if isinstance(reference, str):
        _, reference = _parse_json(reference)
    found_ref, expected = _dig(reference, field)
    if not found_ref:
        return Outcome.UNKNOWN, f"reference has no field {field!r}"
    ok, value = _parse_json(trace.output)
    if not ok:
        return Outcome.FAIL, "output is not valid JSON"
    found, actual = _dig(value, field)
    if not found:
        return Outcome.FAIL, f"output has no field {field!r}"
    return _result(
        actual == expected, f"{field} matches", f"{field} is {actual!r}, expected {expected!r}"
    )


def _pii(example: Example, trace: Trace, options: Mapping[str, Any]) -> CheckResult:
    kinds = options.get("patterns", sorted(_PII))
    found = [kind for kind in kinds if _PII[kind].search(trace.output)]
    return _result(not found, "no personal data found", f"found: {', '.join(found)}")


CHECKS: dict[str, tuple[CheckFunction, tuple[str, ...]]] = {
    "exact_match": (_exact_match, ()),
    "contains": (_contains, ("value",)),
    "not_contains": (_not_contains, ("value",)),
    "regex": (_regex, ("pattern",)),
    "max_words": (_max_words, ("value",)),
    "min_words": (_min_words, ("value",)),
    "max_chars": (_max_chars, ("value",)),
    "not_empty": (_not_empty, ()),
    "one_of": (_one_of, ("values",)),
    "valid_json": (_valid_json, ()),
    "json_schema": (_json_schema, ("schema",)),
    "field_match": (_field_match, ("field",)),
    "pii": (_pii, ()),
}


class CodeCheckJudge:
    """A deterministic check used as a judge, e.g. ``CodeCheckJudge("max_words", value=150)``."""

    def __init__(self, check: str, **options: Any) -> None:
        if check not in CHECKS:
            raise ValueError(
                f"unknown code check {check!r}; available: {', '.join(sorted(CHECKS))}"
            )
        _, required = CHECKS[check]
        missing = [name for name in required if name not in options]
        if missing:
            raise ValueError(f"code check {check!r} needs option(s): {', '.join(missing)}")
        if check == "regex":
            re.compile(str(options["pattern"]))  # fail at config time, not mid-run
        if check == "pii":
            unknown = set(options.get("patterns", [])) - set(_PII)
            if unknown:
                raise ValueError(f"unknown PII pattern(s): {', '.join(sorted(unknown))}")
        self.check = check
        self.options = options
        self.judge_id = content_id(["code-check-v1", check, options])

    async def judge(self, example: Example, trace: Trace, criterion: Criterion) -> Verdict:
        function, _ = CHECKS[self.check]
        outcome, reasoning = function(example, trace, self.options)
        return Verdict(
            trace_id=trace.id,
            criterion_id=criterion.id,
            judge_id=self.judge_id,
            outcome=outcome,
            reasoning=reasoning,
        )
