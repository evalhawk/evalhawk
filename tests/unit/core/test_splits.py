import pytest
from hypothesis import given
from hypothesis import strategies as st

from evalhawk.core.models import Example, Split
from evalhawk.core.splits import SplitSet, assign_split, diagnose_splits, split_key


def test_group_members_share_assignment_and_tags_do_not_affect_it() -> None:
    config = SplitSet(salt="v1")
    first = Example(input="refund?", group_id="seed-1", tags=("billing",))
    second = Example(input="money back?", group_id="seed-1", tags=("refund",))
    assert split_key(first) == split_key(second)
    assert config.assign(first) == config.assign(second)
    assert split_key(Example(input="refund?")) != split_key(first)


@pytest.mark.parametrize("ratios", [(0.2, 0.2, 0.2), (-0.1, 0.5, 0.6), (float("nan"), 0.4, 0.6)])
def test_invalid_ratios_refused(ratios: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError, match="ratios"):
        assign_split("key", salt="v1", ratios=ratios)


def test_zero_buckets_and_split_configuration_identity() -> None:
    assert assign_split("key", salt="v1", ratios=(0, 0, 1)) == Split.TEST
    assert SplitSet(salt="v1").id != SplitSet(salt="v2").id
    assert SplitSet(salt="v1").id != SplitSet(salt="v1", ratios=(0.3, 0.3, 0.4)).id


def test_large_sample_distribution() -> None:
    counts = {pile: 0 for pile in Split}
    for index in range(10_000):
        counts[assign_split(str(index), salt="v1")] += 1
    for pile, ratio in zip(Split, (0.2, 0.4, 0.4), strict=True):
        assert abs(counts[pile] / 10_000 - ratio) < 0.02


def test_split_goldens_and_key_namespaces() -> None:
    config = SplitSet()
    assert config.id == "9a378b3d7bb7061602bd3a892ae4b69fd9a76811fc68fed6fb62991a9bde123f"
    assert [assign_split(key, salt="v1") for key in ("alpha", "beta", "gamma")] == [Split.DEV] * 3
    plain = Example(input="question")
    assert split_key(plain) != split_key(Example(input="different", group_id=plain.id))


@given(st.text(min_size=1))
def test_assignment_is_repeatable(key: str) -> None:
    assert assign_split(key, salt="v1") == assign_split(key, salt="v1")


def test_diagnostics_report_thin_tags_and_few_groups() -> None:
    examples = [Example(input=str(index), group_id="seed", tags=("billing",)) for index in range(3)]
    report = diagnose_splits(SplitSet(), examples)
    assert sum(report.counts.values()) == 3
    assert report.distinct_keys == 1
    assert any("tag billing" in message for message in report.warnings)
    assert any("dominates" in message for message in report.warnings)


def test_empty_keys_invalid_diagnostics_and_healthy_piles() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        assign_split("", salt="v1")
    with pytest.raises(ValueError, match="three"):
        assign_split("key", salt="v1", ratios=(float("inf"), 0, 0))
    with pytest.raises(ValueError, match="non-negative"):
        diagnose_splits(SplitSet(), [], minimum_groups=-1)
    with pytest.raises(ValueError, match="maximum_group_fraction"):
        diagnose_splits(SplitSet(), [], maximum_group_fraction=0)
    examples = [Example(input=str(index), tags=("topic",)) for index in range(100)]
    report = diagnose_splits(SplitSet(), examples, minimum_per_pile=0)
    assert report.warnings == ()
