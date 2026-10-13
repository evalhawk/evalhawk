from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from evalhawk.core.errors import DataError
from evalhawk.core.models import (
    Calibration,
    Criterion,
    Evaluation,
    Example,
    Label,
    Outcome,
    Run,
    TargetOutput,
    Trace,
)
from evalhawk.core.results import Estimate


def test_example_normalizes_text_and_preserves_meaningful_spaces() -> None:
    first = Example(input=" Cafe\u0301\r\nrefund? ", tags=("billing",))
    second = Example(input=" Caf\u00e9\nrefund? ", tags=("refund",))
    assert first.input == " Caf\u00e9\nrefund? "
    assert first.id == second.id


def test_example_rejects_wrong_id_extra_fields_and_mutation() -> None:
    with pytest.raises(ValidationError, match="id"):
        Example(input="question", id="wrong")
    with pytest.raises(ValidationError, match="extra"):
        Example.model_validate({"input": "question", "typo": True})
    example = Example(input="question")
    with pytest.raises(ValidationError, match="frozen"):
        example.input = "changed"


def test_rag_requires_contexts_but_accepts_empty_retrieval() -> None:
    evaluation = Evaluation(dataset_id="support", kind="rag", criteria={"correct": "judge"})
    with pytest.raises(DataError, match="contexts"):
        evaluation.check_shape(Example(input="question"), TargetOutput(output="answer"))
    evaluation.check_shape(Example(input="question"), TargetOutput(output="answer", contexts=()))


def test_model_identity_goldens_and_json_round_trips() -> None:
    example = Example(input="question")
    run = Run(target_version="v1", created_at=datetime(2026, 10, 11, tzinfo=UTC))
    trace = Trace(example_id=example.id, run_id=run.id, output="answer")
    criterion = Criterion(name="correct", question="Correct?")
    label = Label(
        trace_id=trace.id, criterion_id=criterion.id, outcome=Outcome.PASS, annotator="human"
    )
    for record, expected in (
        (example, "307ddeb9d062f504d37900cef65b12dc291f1b3e81d4dd22c3a57f38012288c8"),
        (run, "5f3a9607198a19198da6247946d35b916ed457cd27a342db034a63e49ac98805"),
        (trace, "4c16b7ee9d06c8c57c1f698aa398ffa254b288cebf23360ca487465f557306c6"),
        (criterion, "0912b342724cc9329860f561c4a0be49c29f1a7c208276a3398b16ae3342dae4"),
        (label, "4744312318ea7a6233b79d1e84470f84f01b9bd32eb5625c121f0b2e886a9190"),
    ):
        assert record.id == expected
        assert type(record).model_validate_json(record.model_dump_json()) == record
    assert (
        trace.id != Trace(example_id=example.id, run_id=run.id, output="answer", repeat_index=1).id
    )


@pytest.mark.parametrize("group", ["", " group", "group ", "bad\x00group", 17])
def test_invalid_group_names_rejected(group: object) -> None:
    with pytest.raises(ValidationError, match="group_id"):
        Example.model_validate({"input": "question", "group_id": group})


def test_naive_run_timestamp_and_nonfinite_json_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        Run(target_version="v1", created_at=datetime(2026, 10, 11))
    with pytest.raises(ValueError, match="NaN|finite"):
        Example(input={"value": float("nan")})


def test_calibration_preserves_estimate_contract() -> None:
    estimate = Estimate(point=0.9, low=0.8, high=1, n=100, method="wilson")
    calibration = Calibration(
        judge_id="judge",
        criterion_id="criterion",
        sensitivity=estimate,
        specificity=estimate,
        n=200,
    )
    assert Calibration.model_validate_json(calibration.model_dump_json()) == calibration
