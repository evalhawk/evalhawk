"""Tests for content-addressed IDs (card D1, ADR-0006).

A content ID is a fingerprint of data: the same content always gives the same ID,
on every machine, forever. The golden tests below freeze the exact output. If one
of them fails, you have changed a one-way door: every stored ID would change.
"""

import hashlib
import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from evalhawk.core.ids import MAX_DEPTH, content_id, normalize_text

# --------------------------------------------------------------------------- golden
# The expected hashes were computed independently of our code, with
# hashlib.sha256 on hand-written canonical JSON. They must never change.
GOLDEN = [
    (
        {"input": "What's your refund policy?"},
        '{"input":"What\'s your refund policy?"}',
        "81e2edf761e35614843307ad7c48177b3192197369165cd8d9a864ba58abfd93",
    ),
    (
        {"b": 1, "a": "x"},  # keys deliberately out of order
        '{"a":"x","b":1}',
        "cdab067e9f3beb32d1252cfd63e492592fecbf591b0d08cadb24bb17f3864246",
    ),
    (
        [1, 2.5, True, None, "café"],  # non-ASCII stays as UTF-8, not \u escapes
        '[1,2.5,true,null,"café"]',
        "e5eec6cd5ed8508d7dfdbb4d9df6a0272bd76be282529e1d672568cf2754425b",
    ),
    (
        "hello",
        '"hello"',
        "5aa762ae383fbb727af3c7a36d4940a5b8c40a989452d2304fc958ff3f354e7a",
    ),
]


@pytest.mark.parametrize(("obj", "canonical", "expected"), GOLDEN)
def test_golden_ids_never_change(obj: object, canonical: str, expected: str) -> None:
    # The hard-coded value really is SHA-256 of the canonical text...
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == expected
    # ...and our function produces exactly that.
    assert content_id(obj) == expected


def test_id_is_64_lowercase_hex_characters() -> None:
    cid = content_id({"input": "hi"})
    assert len(cid) == 64
    assert all(ch in "0123456789abcdef" for ch in cid)


# ------------------------------------------------------------------ same content
def test_nested_key_order_does_not_matter() -> None:
    a = {"outer": {"y": 2, "x": 1}, "list": [{"b": 1, "a": 2}]}
    b = {"list": [{"a": 2, "b": 1}], "outer": {"x": 1, "y": 2}}
    assert content_id(a) == content_id(b)


@given(st.dictionaries(st.text(), st.integers(), max_size=20))
def test_key_order_never_changes_the_id(d: dict[str, int]) -> None:
    reversed_order = dict(reversed(list(d.items())))
    assert content_id(d) == content_id(reversed_order)


# ------------------------------------------------------------- different content
def test_any_change_gives_a_different_id() -> None:
    assert content_id({"input": "refund"}) != content_id({"input": "refunds"})


def test_list_order_matters() -> None:
    # Unlike dict keys, list order is part of the content.
    assert content_id([1, 2]) != content_id([2, 1])


def test_types_are_not_confused() -> None:
    # 1, 1.0, True and "1" are different values, so they get different IDs.
    ids = {content_id(1), content_id(1.0), content_id(True), content_id("1")}
    assert len(ids) == 4


# ---------------------------------------------------------------- rejected input
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_nan_and_infinity_are_rejected(bad: float) -> None:
    # NaN and Infinity aren't valid JSON, and NaN != NaN would break identity.
    with pytest.raises(ValueError, match="NaN or Infinity"):
        content_id({"score": bad})


def test_non_string_keys_are_rejected() -> None:
    # json.dumps would silently turn 1 into "1", so {1: "a"} and {"1": "a"}
    # would collide. We refuse instead.
    with pytest.raises(TypeError, match="keys must be strings"):
        content_id({1: "a"})


def test_nested_non_string_keys_are_rejected() -> None:
    with pytest.raises(TypeError, match="keys must be strings"):
        content_id({"outer": [{2: "b"}]})


@pytest.mark.parametrize("bad", [{1, 2}, b"bytes", object()])
def test_non_json_types_are_rejected(bad: object) -> None:
    with pytest.raises(TypeError):
        content_id({"value": bad})


# ------------------------------------------------------------------- nesting depth
def _nested(levels: int) -> object:
    """Build {"k": {"k": ... "leaf" ...}} with `levels` dicts."""
    data: object = "leaf"
    for _ in range(levels):
        data = {"k": data}
    return data


def test_nesting_up_to_the_limit_is_allowed() -> None:
    assert len(content_id(_nested(MAX_DEPTH))) == 64


def test_nesting_beyond_the_limit_is_rejected_clearly() -> None:
    with pytest.raises(ValueError, match=f"nested more than {MAX_DEPTH} levels"):
        content_id(_nested(MAX_DEPTH + 1))


def test_absurd_nesting_gives_our_error_not_a_recursion_error() -> None:
    # Python's own recursion limit is ~1,000 and varies with the call stack.
    # Our explicit limit must trigger first, the same way on every machine.
    with pytest.raises(ValueError, match="nested more than"):
        content_id(_nested(5_000))


# ---------------------------------------------------------------- normalize_text
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\r\nb", "a\nb"),  # Windows line endings
        ("a\rb", "a\nb"),  # old Mac line endings
        ("a\nb", "a\nb"),  # already LF: unchanged
        ("a\r\n\r\nb", "a\n\nb"),  # blank lines are kept
        ("", ""),
    ],
)
def test_normalize_text_converts_line_endings_to_lf(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_same_template_gets_same_id_on_windows_and_linux() -> None:
    windows = "Is the answer polite?\r\nAnswer PASS or FAIL.\r\n"
    linux = "Is the answer polite?\nAnswer PASS or FAIL.\n"
    assert content_id(normalize_text(windows)) == content_id(normalize_text(linux))
