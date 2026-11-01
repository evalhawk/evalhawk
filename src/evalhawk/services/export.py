"""Export a run's traces, verdicts and human labels for use in other tools."""

from collections.abc import Iterator
from typing import Any

from evalhawk.core.models import Split
from evalhawk.core.protocols import Store
from evalhawk.services.calibrate import run_criteria
from evalhawk.services.estimate import adjudicate


def export_rows(store: Store, run_id: str, split_set_id: str) -> Iterator[dict[str, Any]]:
    """One row per trace with every criterion's verdict and adjudicated human label.

    Reading the test pile here is logged in the audit trail (purpose "export").
    """
    run = store.get_run(run_id)
    if run is None:
        return
    criteria = run_criteria(run)
    rows: dict[str, dict[str, Any]] = {}
    for item in criteria:
        for pile in Split:
            outcome_rows = list(
                store.outcome_rows(
                    run_id=run_id,
                    criterion_id=item["criterion_id"],
                    judge_id=item["judge_id"],
                    split_set_id=split_set_id,
                    split=pile,
                    purpose=f"export run={run_id}",
                    include_labels=True,
                )
            )
            by_trace: dict[str, list[Any]] = {}
            for row in outcome_rows:
                by_trace.setdefault(row.trace_id, []).append(row)
            for trace_id, annotations in by_trace.items():
                first = annotations[0]
                record = rows.get(trace_id)
                if record is None:
                    trace = store.get_trace(trace_id)
                    example = store.get_example(first.example_id)
                    record = {
                        "example_id": first.example_id,
                        "trace_id": trace_id,
                        "split": pile.value,
                        "repeat_index": first.repeat_index,
                        "group_id": first.group_id,
                        "input": example.input if example else None,
                        "reference": example.reference if example else None,
                        "output": trace.output if trace else None,
                        "contexts": list(trace.contexts) if trace and trace.contexts else None,
                    }
                    rows[trace_id] = record
                verdict = store.get_verdict(trace_id, item["criterion_id"], item["judge_id"])
                key = f"{item['name']}[{item['judge']}]"
                record[f"{key}.judge"] = None if first.judge_missing else first.judge.value
                record[f"{key}.reasoning"] = verdict.reasoning if verdict else None
                human = adjudicate(annotations)
                record[f"{item['name']}.human"] = human.value if human else None
    yield from rows.values()
