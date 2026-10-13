"""Validated evaluation records; no database or vendor dependencies."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from evalhawk.core.errors import DataError
from evalhawk.core.ids import content_id, normalize_text
from evalhawk.core.results import Estimate


def _text(value: str) -> str:
    return normalize_text(value)


def _identifier(value: str) -> str:
    value = normalize_text(value)
    if not value or value != value.strip() or "\x00" in value:
        raise ValueError("identifier must be non-empty, without edge whitespace or NUL")
    return value


def _json_text(value: JsonValue) -> JsonValue:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [_json_text(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_text(item) for key, item in value.items()}
    return value


Text = Annotated[str, AfterValidator(_text)]
Identifier = Annotated[str, AfterValidator(_identifier)]
NormalizedJSON = Annotated[JsonValue, AfterValidator(_json_text)]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Outcome(StrEnum):
    """PASS is positive; UNKNOWN remains stored rather than becoming FAIL."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Split(StrEnum):
    """Fixed evaluation piles."""

    TRAIN = "train"
    DEV = "dev"
    TEST = "test"


class Record(BaseModel):
    """Reject unknown fields and mutation of record attributes."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", allow_inf_nan=False, validate_default=True
    )


class IdentifiedRecord(Record):
    """Compute an ID from validated identity fields, or verify a supplied ID."""

    id: str = ""

    def identity(self) -> object:
        """Return the canonical, versioned identity payload."""
        raise NotImplementedError

    @model_validator(mode="after")
    def verify_id(self) -> Self:
        expected = content_id(self.identity())
        if self.id and self.id != expected:
            raise ValueError("id does not match validated content; omit id to compute it")
        object.__setattr__(self, "id", expected)
        return self


class Example(IdentifiedRecord):
    """One input; group_id expresses dependence and tags express report categories."""

    input: NormalizedJSON
    reference: NormalizedJSON = None
    group_id: Identifier | None = None
    tags: tuple[Identifier, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    def identity(self) -> object:
        return ["example-v1", self.input, self.reference]


class Run(IdentifiedRecord):
    """One execution; persist created_at when resuming or re-importing a run."""

    target_version: Identifier
    config_snapshot: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    def identity(self) -> object:
        return [
            "run-v1",
            self.target_version,
            self.config_snapshot,
            self.created_at.astimezone(UTC).isoformat(),
        ]


class TargetOutput(Record):
    """A target's answer before a service assigns its run and example IDs."""

    output: Text
    contexts: tuple[Text, ...] | None = None
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    latency_ms: NonNegative = 0


class Trace(TargetOutput, IdentifiedRecord):
    """One output in a run; repeat_index distinguishes repeated executions."""

    example_id: Identifier
    run_id: Identifier
    repeat_index: Annotated[int, Field(ge=0)] = 0

    def identity(self) -> object:
        return [
            "trace-v1",
            self.example_id,
            self.run_id,
            self.repeat_index,
            self.output,
            self.contexts,
        ]


class Criterion(IdentifiedRecord):
    """One versioned binary question."""

    name: Identifier
    question: Text
    version: Annotated[int, Field(ge=1)] = 1

    def identity(self) -> object:
        return ["criterion-v1", self.name, self.question, self.version]


class Verdict(Record):
    """A judge's answer, keyed by trace, criterion and judge identity."""

    trace_id: Identifier
    criterion_id: Identifier
    judge_id: Identifier
    outcome: Outcome
    probability: Probability | None = None
    reasoning: str | None = None
    cost_usd: NonNegative = 0
    latency_ms: NonNegative = 0
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


class Label(IdentifiedRecord):
    """An immutable annotation; a changed answer has a different identity."""

    trace_id: Identifier
    criterion_id: Identifier
    outcome: Outcome
    annotator: Identifier
    note: str | None = None
    inclusion_prob: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 1
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    def identity(self) -> object:
        return [
            "label-v1",
            self.trace_id,
            self.criterion_id,
            self.annotator,
            self.outcome,
            self.note,
            self.inclusion_prob,
        ]


class Evaluation(IdentifiedRecord):
    """Evaluation configuration and load-time shape requirements."""

    dataset_id: Identifier
    kind: Literal["single_turn", "rag"] = "single_turn"
    criteria: dict[str, str]
    estimator: Literal["rogan_gladen", "ppi"] = "rogan_gladen"
    repeats: Annotated[int, Field(ge=1)] = 1

    def identity(self) -> object:
        return [
            "evaluation-v1",
            self.dataset_id,
            self.kind,
            self.criteria,
            self.estimator,
            self.repeats,
        ]

    def check_shape(self, example: Example, output: TargetOutput | None) -> None:
        """Reject missing outputs/contexts before evaluation calls are scheduled."""
        if output is None:
            raise DataError(f"example {example.id}: missing output; supply recorded output")
        if self.kind == "rag" and output.contexts is None:
            raise DataError(f"example {example.id}: rag requires contexts; supply a list")


class Calibration(Record):
    """Human-measured accuracy for one judge and criterion, including intervals."""

    judge_id: Identifier
    criterion_id: Identifier
    sensitivity: Estimate
    specificity: Estimate
    n: Annotated[int, Field(ge=0)]
    computed_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["ok", "stale", "insufficient"] = "ok"
