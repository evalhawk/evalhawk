"""A custom judge: plain Python, no LLM. Any function (example, trace, criterion) -> bool works."""

import re

from evalhawk.core.models import Criterion, Example, Trace

WORD = re.compile(r"[a-z0-9]+")


def grounded(example: Example, trace: Trace, criterion: Criterion) -> bool:
    """PASS when every number in the answer also appears in a retrieved context.

    A crude but useful hallucination check: invented figures ("60 days") fail.
    """
    numbers = {w for w in WORD.findall(trace.output.lower()) if w.isdigit()}
    context = " ".join(trace.contexts or ()).lower()
    return all(n in WORD.findall(context) for n in numbers)
