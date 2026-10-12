"""Offline model doubles and a separate dictionary-based Store implementation."""

import math
from collections.abc import Iterable, Iterator, Mapping

import numpy as np

from evalhawk.core.errors import DataError, StoreError
from evalhawk.core.ids import content_id
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
from evalhawk.core.protocols import OutcomeRow, PairedRecord
from evalhawk.core.splits import SplitSet, split_key


class FakeTarget:
    """Return supplied outputs keyed by example ID; never make model calls."""

    def __init__(self, outputs: Mapping[str, TargetOutput]) -> None:
        self.outputs = dict(outputs)

    async def __call__(self, example: Example) -> TargetOutput:
        try:
            return self.outputs[example.id].model_copy(deep=True)
        except KeyError as exc:
            raise DataError(f"FakeTarget has no output for example {example.id}") from exc


class FakeJudge:
    """Sample Bernoulli judgments with configured sensitivity/specificity, not exact counts."""

    def __init__(
        self,
        sensitivity: float,
        specificity: float,
        *,
        truth: Mapping[str, Outcome],
        rng: np.random.Generator,
    ) -> None:
        if any(
            not math.isfinite(value) or not 0 <= value <= 1 for value in (sensitivity, specificity)
        ):
            raise ValueError("sensitivity and specificity must be finite probabilities")
        self.sensitivity = float(sensitivity)
        self.specificity = float(specificity)
        self.truth = dict(truth)
        self.rng = rng
        self.judge_id = content_id(["fake-judge-v1", self.sensitivity, self.specificity])

    async def judge(self, trace: Trace, criterion: Criterion) -> Verdict:
        """Grade against the separately supplied truth; preserve UNKNOWN ground truth."""
        try:
            truth = self.truth[trace.id]
        except KeyError as exc:
            raise DataError(f"FakeJudge has no truth for trace {trace.id}") from exc
        probability = self.sensitivity if truth == Outcome.PASS else 1 - self.specificity
        outcome = (
            Outcome.UNKNOWN
            if truth == Outcome.UNKNOWN
            else Outcome.PASS
            if self.rng.random() < probability
            else Outcome.FAIL
        )
        return Verdict(
            trace_id=trace.id, criterion_id=criterion.id, judge_id=self.judge_id, outcome=outcome
        )


class InMemoryStore:
    """A non-SQL Store with atomic validation and frozen per-set grouping snapshots."""

    def __init__(self) -> None:
        self.examples: dict[str, Example] = {}
        self.runs: dict[str, Run] = {}
        self.traces: dict[str, Trace] = {}
        self.criteria: dict[str, Criterion] = {}
        self.verdicts: dict[tuple[str, str, str], Verdict] = {}
        self.labels: dict[str, Label] = {}
        self.split_sets: dict[str, SplitSet] = {}
        self.splits: dict[tuple[str, str], tuple[str, Split, str | None]] = {}
        self.test_access_log: list[tuple[str, str]] = []

    def add_examples(self, examples: Iterable[Example]) -> None:
        staged = {
            example.id: Example.model_validate_json(example.model_dump_json())
            for example in examples
        }
        self.examples.update(staged)

    def add_run(self, run: Run) -> None:
        self.runs.setdefault(run.id, Run.model_validate_json(run.model_dump_json()))

    def add_traces(self, run: Run, traces: Iterable[Trace]) -> None:
        staged: dict[str, Trace] = {}
        for trace in traces:
            if trace.example_id not in self.examples:
                raise StoreError("trace references missing example; add examples first")
            if trace.run_id != run.id:
                raise DataError("trace run_id differs from supplied run")
            for previous in (*self.traces.values(), *staged.values()):
                if (previous.example_id, previous.run_id, previous.repeat_index) == (
                    trace.example_id,
                    trace.run_id,
                    trace.repeat_index,
                ) and previous.id != trace.id:
                    raise DataError("trace repeat slot already contains another output")
            staged[trace.id] = Trace.model_validate_json(trace.model_dump_json())
        self.add_run(run)
        self.traces.update(staged)

    def add_criterion(self, criterion: Criterion) -> None:
        self.criteria.setdefault(
            criterion.id, Criterion.model_validate_json(criterion.model_dump_json())
        )

    def assign_splits(self, config: SplitSet, examples: Iterable[Example]) -> None:
        config = SplitSet.model_validate_json(config.model_dump_json())
        if any(
            previous.salt == config.salt and previous.id != config.id
            for previous in self.split_sets.values()
        ):
            raise DataError("salt already identifies different ratios/by; choose a new salt")
        staged: dict[tuple[str, str], tuple[str, Split, str | None]] = {}
        for example in examples:
            Example.model_validate_json(example.model_dump_json())
            if example.id not in self.examples:
                raise StoreError("split references missing example; add examples first")
            index = (config.id, example.id)
            key = split_key(example, by=config.by)
            previous = self.splits.get(index) or staged.get(index)
            if previous and previous[0] != key:
                raise DataError("group changed in a locked split set; choose a new salt")
            staged[index] = previous or (key, config.assign(example), example.group_id)
        self.split_sets.setdefault(config.id, config)
        self.splits.update(staged)

    def get_split(self, split_set_id: str, example_id: str) -> Split | None:
        row = self.splits.get((split_set_id, example_id))
        return row[1] if row else None

    def get_verdict(self, trace_id: str, criterion_id: str, judge_id: str) -> Verdict | None:
        verdict = self.verdicts.get((trace_id, criterion_id, judge_id))
        return verdict.model_copy(deep=True) if verdict else None

    def put_verdict(self, verdict: Verdict) -> None:
        if verdict.trace_id not in self.traces or verdict.criterion_id not in self.criteria:
            raise StoreError("verdict references missing trace or criterion")
        key = (verdict.trace_id, verdict.criterion_id, verdict.judge_id)
        previous = self.verdicts.get(key)
        if previous and (previous.outcome, previous.probability) != (
            verdict.outcome,
            verdict.probability,
        ):
            raise DataError("cached verdict differs; use a new judge_id")
        self.verdicts.setdefault(key, Verdict.model_validate_json(verdict.model_dump_json()))

    def add_label(self, label: Label) -> None:
        if label.trace_id not in self.traces or label.criterion_id not in self.criteria:
            raise StoreError("label references missing trace or criterion")
        self.labels.setdefault(label.id, Label.model_validate_json(label.model_dump_json()))

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
        if not purpose.strip():
            raise DataError("purpose must describe why outcomes are being read")
        if split == Split.TEST:
            if split_set_id not in self.split_sets:
                raise StoreError("missing split set")
            self.test_access_log.append((split_set_id, purpose))
        for trace in sorted(
            self.traces.values(), key=lambda item: (item.example_id, item.repeat_index)
        ):
            row = self.splits.get((split_set_id, trace.example_id))
            if trace.run_id != run_id or row is None or row[1] != split:
                continue
            if tag is not None and tag not in self.examples[trace.example_id].tags:
                continue
            verdict = self.get_verdict(trace.id, criterion_id, judge_id)
            if verdict is None:
                continue
            labels = sorted(
                (
                    label
                    for label in self.labels.values()
                    if label.trace_id == trace.id and label.criterion_id == criterion_id
                ),
                key=lambda item: item.id,
            )
            for label in labels or [None]:
                yield PairedRecord(
                    trace.example_id,
                    row[2],
                    trace.id,
                    verdict.outcome,
                    label.outcome if label else None,
                    label.annotator if label else None,
                    label.inclusion_prob if label else None,
                )

    def split_counts(self, split_set_id: str, *, tag: str | None = None) -> dict[Split, int]:
        counts = dict.fromkeys(Split, 0)
        for (config_id, example_id), (_, pile, _) in self.splits.items():
            if config_id == split_set_id and (tag is None or tag in self.examples[example_id].tags):
                counts[pile] += 1
        return counts

    def close(self) -> None:
        """No resources to release in this implementation."""

    def find_runs(self, target_version: str) -> list[Run]:
        """Return defensive copies of matching executions."""
        return [
            run.model_copy(deep=True)
            for run in self.runs.values()
            if run.target_version == target_version
        ]

    def test_reads(self, split_set_id: str) -> list[tuple[str, str]]:
        """The fake has deterministic timestamps rather than a real clock."""
        return [
            (purpose, "fake-clock")
            for config, purpose in self.test_access_log
            if config == split_set_id
        ]

    def get_run(self, run_id: str) -> Run | None:
        """Read a defensive execution copy."""
        run = self.runs.get(run_id)
        return run.model_copy(deep=True) if run else None

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
        """Expose scalar annotation metadata with the same audit semantics as SQLite."""
        if not purpose.strip():
            raise DataError("purpose must describe why outcomes are being read")
        if split == Split.TEST:
            if split_set_id not in self.split_sets:
                raise StoreError("missing split set")
            self.test_access_log.append((split_set_id, purpose))
        for trace in sorted(
            self.traces.values(), key=lambda item: (item.example_id, item.repeat_index)
        ):
            assignment = self.splits.get((split_set_id, trace.example_id))
            if trace.run_id != run_id or assignment is None or assignment[1] != split:
                continue
            if tag is not None and tag not in self.examples[trace.example_id].tags:
                continue
            verdict = self.get_verdict(trace.id, criterion_id, judge_id)
            labels = sorted(
                (
                    label
                    for label in self.labels.values()
                    if include_labels
                    and label.trace_id == trace.id
                    and label.criterion_id == criterion_id
                ),
                key=lambda item: item.id,
            )
            for label in labels or [None]:
                yield OutcomeRow(
                    trace.example_id,
                    assignment[2],
                    trace.id,
                    trace.repeat_index,
                    verdict.outcome if verdict else Outcome.UNKNOWN,
                    label.outcome if label else None,
                    label.annotator if label else None,
                    label.inclusion_prob if label else None,
                    label.created_at if label else None,
                    verdict is None,
                )
