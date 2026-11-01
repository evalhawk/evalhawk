import numpy as np
import pytest

from evalhawk.clustering.text import cluster_texts, tfidf

TEXTS = (
    [f"says refunds take {d} days but the policy says 30 days" for d in (45, 60, 90, 14)]
    + [
        f"invents a loyalty programme with {p} points"
        for p in ("gold", "silver", "double", "bonus")
    ]
    + [
        f"rude tone, tells the customer to {w}"
        for w in ("go away", "stop asking", "read the faq", "wait")
    ]
)


def test_tfidf_rows_are_unit_vectors_and_common_words_weigh_less() -> None:
    matrix, vocab = tfidf(["refund refund policy", "refund shipping"])
    assert np.allclose(np.linalg.norm(matrix, axis=1), 1.0)
    assert set(vocab) == {"refund", "policy", "shipping"}
    row = dict(zip(vocab, matrix[0], strict=True))
    assert row["policy"] > row["refund"] / 2  # rarer word keeps weight despite fewer counts


def test_three_obvious_themes_are_recovered() -> None:
    clusters = cluster_texts(TEXTS, k=3, rng=np.random.default_rng(0))
    assert [c.size for c in clusters] == [4, 4, 4]
    themes = [set(c.top_terms) for c in clusters]
    assert any("days" in t or "refunds" in t for t in themes)
    assert any("loyalty" in t or "programme" in t for t in themes)
    assert any("rude" in t or "tone" in t for t in themes)
    for cluster in clusters:  # members of one cluster share its theme
        texts = [TEXTS[i] for i in cluster.members]
        assert len({t.split()[0] for t in texts}) == 1


def test_results_are_reproducible_with_a_seed() -> None:
    first = cluster_texts(TEXTS, rng=np.random.default_rng(7))
    second = cluster_texts(TEXTS, rng=np.random.default_rng(7))
    assert first == second


def test_bad_inputs() -> None:
    with pytest.raises(ValueError, match="no texts"):
        cluster_texts([], rng=np.random.default_rng(0))
    with pytest.raises(ValueError, match="informative words"):
        cluster_texts(["the a an", "is it"], rng=np.random.default_rng(0))
