"""Live evaluation: lock splits, run the target and judges, summarise what was judged."""

from collections.abc import Sequence
from dataclasses import dataclass

from evalhawk.core.ids import content_id
from evalhawk.core.models import Example, JsonValue, Outcome, Run, Split
from evalhawk.core.protocols import Store, Target
from evalhawk.core.results import Estimate
from evalhawk.core.splits import SplitSet
from evalhawk.runner.executor import JudgeSpec, RunnerSettings, RunSummary, execute
from evalhawk.stats.intervals import wilson_interval


def run_snapshot(
    *,
    evaluation: str,
    specs: Sequence[JudgeSpec],
    judge_names: Sequence[str],
    splits: SplitSet,
    repeats: int,
    kind: str,
    target: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """The run's saved configuration: identities, never expanded secrets."""
    return {
        "kind": "evaluation",
        "evaluation": evaluation,
        "evaluation_kind": kind,
        "repeats": repeats,
        "splits": splits.model_dump(mode="json"),
        "criteria": [
            {
                "name": spec.criterion.name,
                "criterion_id": spec.criterion.id,
                "judge": judge_name,
                "judge_id": spec.judge.judge_id,
            }
            for spec, judge_name in zip(specs, judge_names, strict=True)
        ],
        "target": target,
    }


def find_or_create_run(
    store: Store, *, target_version: str, snapshot: dict[str, JsonValue], fresh: bool = False
) -> tuple[Run, bool]:
    """Resume the run with the same version and configuration, unless ``fresh``.

    Returns ``(run, resumed)``. A changed configuration (new judge, prompt, criteria or
    splits) always starts a new run, so results from different setups never mix.
    """
    if not fresh:
        for run in store.find_runs(target_version):
            if run.config_snapshot == snapshot:
                return run, True
    return Run(target_version=target_version, config_snapshot=snapshot), False


def sample_examples(examples: Sequence[Example], n: int | None, *, seed: int = 0) -> list[Example]:
    """A reproducible subset: the ``n`` examples with the smallest seeded hash."""
    if n is None or n >= len(examples):
        return list(examples)
    if n < 1:
        raise ValueError("--sample must be at least 1")
    return sorted(examples, key=lambda e: content_id(["sample-v1", seed, e.id]))[:n]


async def run_evaluation(
    store: Store,
    *,
    run: Run,
    examples: Sequence[Example],
    target: Target,
    specs: Sequence[JudgeSpec],
    splits: SplitSet,
    repeats: int = 1,
    settings: RunnerSettings | None = None,
    require_contexts: bool = False,
) -> RunSummary:
    """Store examples, lock their splits (before any outcome exists), then execute."""
    store.add_examples(examples)
    store.assign_splits(splits, examples)
    return await execute(
        store,
        run,
        examples,
        target,
        specs,
        repeats=repeats,
        settings=settings,
        require_contexts=require_contexts,
    )


@dataclass(frozen=True, slots=True)
class JudgedRate:
    """The judge's (uncorrected) pass rate for one criterion over every pile."""

    criterion: str
    judge: str
    rate: Estimate | None
    passes: int
    fails: int
    unknown: int


def judged_rates(store: Store, run: Run, split_set_id: str) -> list[JudgedRate]:
    """Uncorrected judged pass rates; reading the test pile is logged like any other read."""
    criteria = run.config_snapshot.get("criteria")
    out: list[JudgedRate] = []
    for item in criteria if isinstance(criteria, list) else []:
        if not isinstance(item, dict):
            continue
        counts = {Outcome.PASS: 0, Outcome.FAIL: 0, Outcome.UNKNOWN: 0}
        for pile in (Split.TRAIN, Split.DEV, Split.TEST):
            for row in store.outcome_rows(
                run_id=run.id,
                criterion_id=str(item["criterion_id"]),
                judge_id=str(item["judge_id"]),
                split_set_id=split_set_id,
                split=pile,
                purpose=f"eval summary: judged pass rate run={run.id} criterion={item['name']}",
                include_labels=False,
            ):
                if not row.judge_missing:
                    counts[row.judge] += 1
        known = counts[Outcome.PASS] + counts[Outcome.FAIL]
        total = known + counts[Outcome.UNKNOWN]
        rate = None
        if known:
            interval = wilson_interval(counts[Outcome.PASS], known)
            rate = Estimate(
                point=interval.point,
                low=interval.low,
                high=interval.high,
                n=known,
                method="wilson (uncorrected judge)",
                unknown_rate=counts[Outcome.UNKNOWN] / total,
            )
        out.append(
            JudgedRate(
                criterion=str(item["name"]),
                judge=str(item["judge"]),
                rate=rate,
                passes=counts[Outcome.PASS],
                fails=counts[Outcome.FAIL],
                unknown=counts[Outcome.UNKNOWN],
            )
        )
    return out
