"""Blind human labelling: what to label next, and saving labels.

The queue offers the **dev representatives** (one answer per locked group, repeat 0): the
exact items the corrected report uses, so every label counts. The order is a stable
pseudo-random shuffle per annotator, so labelling any prefix of the queue is a random
sample (each label keeps inclusion probability 1). The judge's verdict is read only to
select rows and is **never** returned: labelling is blind.
"""

from dataclasses import dataclass
from itertools import groupby

from evalhawk.core.errors import DataError
from evalhawk.core.ids import content_id
from evalhawk.core.models import Criterion, JsonValue, Label, Outcome, Run, Split
from evalhawk.core.protocols import Store
from evalhawk.core.splits import SplitSet
from evalhawk.services.calibrate import run_criteria


@dataclass(frozen=True, slots=True)
class LabelItem:
    """One answer to label, with everything a human needs and nothing from the judge."""

    trace_id: str
    example_id: str
    criterion: Criterion
    input: JsonValue
    reference: JsonValue
    output: str
    contexts: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class QueueState:
    """The next item (or None when done) and progress for this annotator."""

    item: LabelItem | None
    labelled: int
    total: int


def criterion_entry(run: Run, name: str) -> dict[str, str]:
    """The first (criterion, judge) entry of a run with this criterion name."""
    for item in run_criteria(run):
        if item["name"] == name:
            return item
    names = ", ".join(sorted({item["name"] for item in run_criteria(run)}))
    raise DataError(f"run {run.id[:12]} has no criterion {name!r}; it has: {names}")


def queue(
    store: Store, run: Run, criterion_name: str, *, annotator: str, seed: int = 0
) -> QueueState:
    """The next unlabelled dev representative for ``annotator`` and their progress."""
    entry = criterion_entry(run, criterion_name)
    splits = run.config_snapshot.get("splits")
    if not isinstance(splits, dict):
        raise DataError("run has no saved split configuration")
    split_set = SplitSet.model_validate(splits)
    rows = store.outcome_rows(
        run_id=run.id,
        criterion_id=entry["criterion_id"],
        judge_id=entry["judge_id"],
        split_set_id=split_set.id,
        split=Split.DEV,
        purpose="label queue",
        include_labels=True,
    )
    seen: set[tuple[str, str]] = set()
    candidates: list[str] = []
    labelled: set[str] = set()
    for trace_id, annotations in groupby(rows, key=lambda row: row.trace_id):
        group = list(annotations)
        first = group[0]
        key = ("group", first.group_id) if first.group_id else ("example", first.example_id)
        if key in seen:
            continue
        seen.add(key)
        if first.repeat_index != 0:
            continue
        candidates.append(trace_id)
        if any(row.annotator == annotator for row in group):
            labelled.add(trace_id)
    remaining = sorted(
        (trace_id for trace_id in candidates if trace_id not in labelled),
        key=lambda trace_id: content_id(["label-queue-v1", seed, annotator, trace_id]),
    )
    item = None
    if remaining:
        trace = store.get_trace(remaining[0])
        criterion = store.get_criterion(entry["criterion_id"])
        if trace is None or criterion is None:
            raise DataError("label queue references a missing trace or criterion")
        example = store.get_example(trace.example_id)
        if example is None:
            raise DataError("label queue references a missing example")
        item = LabelItem(
            trace_id=trace.id,
            example_id=example.id,
            criterion=criterion,
            input=example.input,
            reference=example.reference,
            output=trace.output,
            contexts=trace.contexts,
        )
    return QueueState(item=item, labelled=len(labelled), total=len(candidates))


def save_label(
    store: Store,
    *,
    trace_id: str,
    criterion_id: str,
    annotator: str,
    outcome: Outcome,
    note: str | None = None,
) -> Label:
    """Store one human label; history is kept (a later label by the same person wins)."""
    if store.get_trace(trace_id) is None:
        raise DataError(f"no answer {trace_id[:12]} to label")
    label = Label(
        trace_id=trace_id,
        criterion_id=criterion_id,
        outcome=outcome,
        annotator=annotator,
        note=note.strip() if note and note.strip() else None,
    )
    store.add_label(label)
    return label
