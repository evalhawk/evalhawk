import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from evalhawk.stats.selective import cascade_curve, cascade_predictions, error_correlation

#            p(PASS) strong human
DATA = np.array(
    [
        [0.95, 1, 1],  # confident PASS, right
        [0.90, 1, 1],
        [0.10, 0, 0],  # confident FAIL, right
        [0.60, 0, 0],  # unsure (cheap would say PASS, wrong); strong is right
        [0.45, 1, 1],  # unsure (cheap would say FAIL, wrong); strong is right
        [0.85, 0, 0],  # confident PASS, WRONG; strong is right
    ]
)
P, S, H = DATA[:, 0], DATA[:, 1].astype(int), DATA[:, 2].astype(int)


def test_predictions_at_a_threshold() -> None:
    combined, accepted = cascade_predictions(P, S, 0.8)
    assert accepted.tolist() == [True, True, True, False, False, True]
    assert combined.tolist() == [1, 1, 0, 0, 1, 1]  # unsure items take the strong verdict


def test_curve_endpoints_are_cheap_alone_and_strong_alone() -> None:
    curve = cascade_curve(P, S, H)
    first, last = curve.points[0], curve.points[-1]
    assert first.threshold == 0.5
    assert first.coverage == 1.0  # tau=0.5: the cheap judge decides everything
    assert first.accuracy.point == pytest.approx(curve.cheap_accuracy.point)
    assert curve.cheap_accuracy.point == pytest.approx(3 / 6)
    assert last.threshold == 1.0
    assert last.coverage == 0.0  # nobody is 100% sure: everything escalates
    assert last.accuracy.point == pytest.approx(curve.strong_accuracy.point)
    assert curve.strong_accuracy.point == 1.0


def test_target_accuracy_picks_the_cheapest_threshold_that_meets_it() -> None:
    curve = cascade_curve(P, S, H, target_accuracy=0.8)
    assert curve.chosen is not None
    assert curve.chosen.accuracy.point >= 0.8
    eligible = [p for p in curve.points if p.accuracy.point >= 0.8]
    assert curve.chosen.coverage == max(p.coverage for p in eligible)
    assert cascade_curve(P, S, H, target_accuracy=1.0).chosen is not None
    impossible = cascade_curve(P, np.zeros(6, dtype=int), H, target_accuracy=1.0)
    assert impossible.chosen is None


@given(
    st.lists(
        st.tuples(st.floats(0, 1), st.integers(0, 1), st.integers(0, 1)), min_size=1, max_size=40
    )
)
def test_coverage_never_increases_with_the_threshold(rows: list[tuple[float, int, int]]) -> None:
    p, s, h = (np.array(col) for col in zip(*rows, strict=True))
    curve = cascade_curve(p, s, h)
    coverages = [point.coverage for point in curve.points]
    assert coverages == sorted(coverages, reverse=True)
    assert all(point.escalations == round((1 - point.coverage) * len(h)) for point in curve.points)


def test_error_correlation() -> None:
    cheap = np.array([1, 1, 0, 1, 0, 1, 1, 0])
    strong = np.array([1, 1, 0, 1, 1, 1, 0, 1])
    human = np.array([1, 1, 0, 0, 1, 1, 0, 1])
    result = error_correlation(cheap, strong, human)
    # cheap wrong on items 3, 4, 6, 7; strong wrong on item 3 only
    assert result.cheap_wrong.point == pytest.approx(4 / 8)
    assert result.strong_wrong.point == pytest.approx(1 / 8)
    assert result.strong_wrong_given_cheap_wrong is not None
    assert result.strong_wrong_given_cheap_wrong.point == pytest.approx(1 / 4)
    assert result.lift == pytest.approx(2.0)
    perfect = error_correlation(human, human, human)
    assert perfect.strong_wrong_given_cheap_wrong is None
    assert perfect.lift is None


@pytest.mark.parametrize(
    ("p", "message"), [([0.5, float("nan")], "probabilities"), ([1.2], "probabilities")]
)
def test_bad_probabilities_are_refused(p: list[float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        cascade_curve(p, [1] * len(p), [1] * len(p))


def test_threshold_out_of_range() -> None:
    with pytest.raises(ValueError, match="threshold"):
        cascade_predictions([0.7], [1], 0.4)
