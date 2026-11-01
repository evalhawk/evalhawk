"""Judge calibration status: how far each (judge, criterion) can be trusted right now."""

from dataclasses import dataclass
from typing import Literal

from evalhawk.core.models import Outcome, Run, Split
from evalhawk.core.protocols import Store
from evalhawk.core.results import Estimate
from evalhawk.services.estimate import representatives
from evalhawk.stats.intervals import wilson_interval

MIN_LABELS_PER_OUTCOME = 10
"""Below this many resolved human labels of PASS or of FAIL, calibration is insufficient."""


@dataclass(frozen=True, slots=True)
class CalibrationStatus:
    """A judge's report-card summary on the dev pile, with its readiness status."""

    criterion: str
    judge: str
    judge_id: str
    sensitivity: Estimate | None
    specificity: Estimate | None
    n_pass: int
    n_fail: int
    status: Literal["ok", "insufficient"]
    need_more: int


def run_criteria(run: Run) -> list[dict[str, str]]:
    """The (criterion, judge) entries saved in a run's configuration."""
    snapshot = run.config_snapshot
    items = snapshot.get("criteria")
    if isinstance(items, list):
        return [{k: str(v) for k, v in item.items()} for item in items if isinstance(item, dict)]
    criterion_id, judge_id = snapshot.get("criterion_id"), snapshot.get("judge_id")
    if isinstance(criterion_id, str) and isinstance(judge_id, str):  # recorded imports
        return [
            {
                "name": "recorded",
                "criterion_id": criterion_id,
                "judge": judge_id,
                "judge_id": judge_id,
            }
        ]
    return []


def calibration_status(
    store: Store,
    run: Run,
    split_set_id: str,
    *,
    minimum: int = MIN_LABELS_PER_OUTCOME,
) -> list[CalibrationStatus]:
    """Sensitivity and specificity per (judge, criterion) on dev human labels."""
    out: list[CalibrationStatus] = []
    for item in run_criteria(run):
        if item["name"] == "recorded":  # recorded imports: use the stored criterion's name
            stored = store.get_criterion(item["criterion_id"])
            item = {**item, "name": stored.name if stored else item["name"]}
        tp = fn = tn = fp = 0
        rows = store.outcome_rows(
            run_id=run.id,
            criterion_id=item["criterion_id"],
            judge_id=item["judge_id"],
            split_set_id=split_set_id,
            split=Split.DEV,
            purpose="judges status",
            include_labels=True,
        )
        for row, human in representatives(rows):
            if human is None or row.judge is Outcome.UNKNOWN or row.judge_missing:
                continue
            judged_pass = row.judge is Outcome.PASS
            if human is Outcome.PASS:
                tp, fn = tp + judged_pass, fn + (not judged_pass)
            else:
                fp, tn = fp + judged_pass, tn + (not judged_pass)
        n_pass, n_fail = tp + fn, tn + fp
        out.append(
            CalibrationStatus(
                criterion=item["name"],
                judge=item["judge"],
                judge_id=item["judge_id"],
                sensitivity=wilson_interval(tp, n_pass) if n_pass else None,
                specificity=wilson_interval(tn, n_fail) if n_fail else None,
                n_pass=n_pass,
                n_fail=n_fail,
                status="ok" if min(n_pass, n_fail) >= minimum else "insufficient",
                need_more=max(0, minimum - n_pass) + max(0, minimum - n_fail),
            )
        )
    return out
