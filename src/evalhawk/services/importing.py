"""Bounded recorded imports; completed batches survive a later file error."""

from collections.abc import Iterable
from itertools import islice

from evalhawk.core.models import Criterion, Run
from evalhawk.core.protocols import RecordedObservation, Store
from evalhawk.core.splits import SplitSet


def import_recorded(
    store: Store,
    records: Iterable[RecordedObservation],
    *,
    run: Run,
    criterion: Criterion,
    splits: SplitSet,
    batch_size: int = 500,
) -> int:
    """Return processed rows, not unique inserts; reimport the same run to resume."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    count = 0
    iterator = iter(records)
    store.add_run(run)
    store.add_criterion(criterion)
    while batch := tuple(islice(iterator, batch_size)):
        store.add_examples(record.example for record in batch)
        store.assign_splits(splits, (record.example for record in batch))
        store.add_traces(run, (record.trace for record in batch))
        for record in batch:
            store.put_verdict(record.verdict)
            for label in record.labels:
                store.add_label(label)
        count += len(batch)
    return count
