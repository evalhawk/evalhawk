"""A tiny JSONPath subset for reading answers out of API responses.

Supported: ``$``, ``.field``, ``["field"]``, ``[0]`` (index) and ``[*]`` (every item).
Examples: ``$.reply.text``, ``$.choices[0].message.content``, ``$.sources[*].text``.
"""

import re
from typing import Any

_TOKEN = re.compile(r"""\.([A-Za-z_][\w-]*)|\[(\d+)\]|\[\*\]|\["([^"]+)"\]|\['([^']+)'\]""")


def _steps(path: str) -> list[str | int | None]:
    if not path.startswith("$"):
        raise ValueError(f"JSONPath must start with '$': {path!r}")
    steps: list[str | int | None] = []
    position = 1
    while position < len(path):
        match = _TOKEN.match(path, position)
        if not match:
            raise ValueError(f"unsupported JSONPath syntax at {path[position:]!r} in {path!r}")
        name, index, quoted, single = match.groups()
        if name is not None or quoted is not None or single is not None:
            steps.append(name or quoted or single)
        elif index is not None:
            steps.append(int(index))
        else:
            steps.append(None)  # [*]
        position = match.end()
    return steps


def find(document: Any, path: str) -> list[Any]:
    """All values at ``path`` (empty if nothing matches); ``[*]`` can yield many."""
    values = [document]
    for step in _steps(path):
        next_values: list[Any] = []
        for value in values:
            if step is None:
                if isinstance(value, list):
                    next_values.extend(value)
            elif isinstance(step, int):
                if isinstance(value, list) and -len(value) <= step < len(value):
                    next_values.append(value[step])
            elif isinstance(value, dict) and step in value:
                next_values.append(value[step])
        values = next_values
    return values


def validate(path: str) -> None:
    """Raise ValueError now if ``path`` uses unsupported syntax (config-time check)."""
    _steps(path)
