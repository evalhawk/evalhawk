"""Content-addressed IDs (ADR-0006).

A content ID is a fingerprint of data: the SHA-256 hash of the data's canonical
JSON. The same content always gives the same ID, on every machine, forever, which
gives EvalHawk deduplication, caching and reproducibility for free.

This is a one-way door. Changing how the canonical form is built would change every
ID already stored in users' databases, so the exact output is frozen by golden tests
(``tests/unit/core/test_ids.py``).
"""

import hashlib
import json
from typing import Final, cast

MAX_DEPTH: Final = 100
"""Deepest nesting of dicts and lists that ``content_id`` accepts.

Real evaluation data nests a few levels. An explicit limit makes deep input fail the
same way on every machine, with a clear message, long before Python's own recursion
limit (about 1,000, and lower when called from deep inside other code).
"""


def normalize_text(text: str) -> str:
    """Convert Windows (``\\r\\n``) and old Mac (``\\r``) line endings to ``\\n``.

    Use it on text read from files (such as prompt templates) before hashing, so the
    same file gets the same ID whether it was saved on Windows or Linux.

    Args:
        text: Any string.

    Returns:
        The same string with every line ending as ``\\n``.

    Example:
        >>> normalize_text("line one\\r\\nline two")
        'line one\\nline two'
    """
    # "\r\n" must be replaced first: doing "\r" first would turn "\r\n" into "\n\n".
    return text.replace("\r\n", "\n").replace("\r", "\n")


def content_id(obj: object) -> str:
    """Return the content ID of a JSON-compatible value.

    The value is written as canonical JSON (keys sorted, no whitespace, UTF-8,
    no NaN or Infinity) and hashed with SHA-256.

    Args:
        obj: A JSON-compatible value: ``dict`` with ``str`` keys, ``list``,
            ``tuple`` (treated as a list), ``str``, ``int``, ``float``, ``bool``
            or ``None``, nested to any depth.

    Returns:
        64 lowercase hexadecimal characters.

    Raises:
        TypeError: If a dict key anywhere is not a ``str``, or a value is not
            JSON-compatible (for example a ``set``, ``bytes`` or ``datetime``).
        ValueError: If a float anywhere is NaN or Infinity, or the data is nested
            more than ``MAX_DEPTH`` levels deep.

    Example:
        >>> content_id({"b": 1, "a": "x"}) == content_id({"a": "x", "b": 1})
        True
    """
    _check_structure(obj, path="$", depth=1)
    try:
        canonical = json.dumps(
            obj,
            sort_keys=True,  # key order never changes the ID
            separators=(",", ":"),  # no spaces: one exact text for each value
            ensure_ascii=False,  # "café" stays "café", not "café"
            allow_nan=False,  # NaN and Infinity aren't valid JSON
        )
    except ValueError as exc:
        raise ValueError(
            "content_id: NaN or Infinity is not allowed (it isn't valid JSON, and "
            "NaN != NaN, so it can't have a stable identity). Replace it with None "
            "or a finite number."
        ) from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_structure(obj: object, path: str, depth: int) -> None:
    """Walk ``obj`` and reject non-string dict keys and excessive nesting.

    ``json.dumps`` would silently turn the key ``1`` into ``"1"``, so ``{1: "a"}``
    and ``{"1": "a"}`` would get the same ID. We refuse instead of colliding.

    Args:
        obj: The value being checked.
        path: Where ``obj`` sits in the whole value, e.g. ``$.outer[0]``
            (``$`` is the top). Used in error messages.
        depth: How many dicts/lists deep ``obj`` is (the top container is 1).
    """
    if not isinstance(obj, dict | list | tuple):
        return  # a plain value (str, number, bool, None): nothing to walk into
    if depth > MAX_DEPTH:
        shown = path if len(path) <= 60 else path[:57] + "..."
        raise ValueError(
            f"content_id: data is nested more than {MAX_DEPTH} levels deep "
            f"(at {shown}). Flatten it before hashing."
        )
    if isinstance(obj, dict):
        mapping = cast("dict[object, object]", obj)
        for key, value in mapping.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"content_id: dict keys must be strings, but found the "
                    f"{type(key).__name__} key {key!r} at {path}. "
                    f"Convert it with str() before hashing."
                )
            _check_structure(value, f"{path}.{key}", depth + 1)
    else:
        items = cast("list[object] | tuple[object, ...]", obj)
        for index, item in enumerate(items):
            _check_structure(item, f"{path}[{index}]", depth + 1)
