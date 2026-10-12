"""Structural ports: async model calls, streaming sources and synchronous stores."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from evalhawk.core.models import (
    Criterion,
    Example,
    Label,
    Outcome,
    Run,
    Split,
    TargetOutput,
    Trace,
    Verdict,
)
from evalhawk.core.splits import SplitSet


@dataclass(frozen=True, slots=True)
class PairedRecord:
    """Plain joined data; UNKNOWN filtering and label adjudication belong to services."""

    example_id: str
    group_id: str | None
    trace_id: str
    judge: Outcome
    human: Outcome | None
    annotator: str | None
    inclusion_prob: float | None


@runtime_checkable
class Target(Protocol):
    """The user's application, called once for an example."""

    async def __call__(self, example: Example) -> TargetOutput: ...


@runtime_checkable
class Judge(Protocol):
    """A judge identity and one binary judgment."""

    @property
    def judge_id(self) -> str: ...

    async def judge(self, trace: Trace, criterion: Criterion) -> Verdict: ...


@runtime_checkable
class MultiCriterionJudge(Judge, Protocol):
    """Optional capability for grading several criteria in one call."""

    async def judge_many(self, trace: Trace, criteria: list[Criterion]) -> list[Verdict]: ...


class TraceSource(Protocol):
    """Stream inputs and optional outputs; the import service supplies run identity."""

    def load(self) -> Iterable[tuple[Example, TargetOutput | None]]: ...


@dataclass(frozen=True, slots=True)
class RecordedObservation:
    """A validated recorded output and its judge/human annotations."""

    example: Example
    trace: Trace
    verdict: Verdict
    labels: tuple[Label, ...]


class Store(Protocol):
    """Sync state access; concrete implementations must preserve split history."""

    def add_examples(self, examples: Iterable[Example]) -> None: ...
    def add_run(self, run: Run) -> None: ...
    def add_traces(self, run: Run, traces: Iterable[Trace]) -> None: ...
    def add_criterion(self, criterion: Criterion) -> None: ...
    def assign_splits(self, config: SplitSet, examples: Iterable[Example]) -> None: ...
    def get_split(self, split_set_id: str, example_id: str) -> Split | None: ...
    def get_verdict(self, trace_id: str, criterion_id: str, judge_id: str) -> Verdict | None: ...
    def put_verdict(self, verdict: Verdict) -> None: ...
    def add_label(self, label: Label) -> None: ...
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
    ) -> Iterator[PairedRecord]: ...
    def split_counts(self, split_set_id: str, *, tag: str | None = None) -> dict[Split, int]: ...
    def find_runs(self, target_version: str) -> list[Run]: ...
    def get_run(self, run_id: str) -> Run | None: ...
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
    ) -> Iterator[OutcomeRow]: ...
    def test_reads(self, split_set_id: str) -> list[tuple[str, str]]: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class OutcomeRow:
    """Lean joined outcomes, ordered by example and repeat, without output text."""

    example_id: str
    group_id: str | None
    trace_id: str
    repeat_index: int
    judge: Outcome
    human: Outcome | None
    annotator: str | None
    inclusion_prob: float | None
    label_time: datetime | None
    judge_missing: bool = False
