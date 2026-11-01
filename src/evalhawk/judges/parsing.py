"""Strict parsing of a judge's free-text reply into PASS, FAIL or UNKNOWN."""

import re

from evalhawk.core.models import Outcome

_VERDICT = re.compile(r"\bVERDICT\s*[:=]\s*\**\s*(PASS|FAIL|UNKNOWN)\b", re.IGNORECASE)
_BARE = re.compile(r"^\W*(PASS|FAIL|UNKNOWN)\W*$", re.IGNORECASE)


def parse_verdict(text: str) -> tuple[Outcome, str | None, bool]:
    """Return ``(outcome, reasoning, parsed)``.

    Accepts a final ``VERDICT: PASS|FAIL|UNKNOWN`` line (the last one wins, so the judge
    may discuss verdicts while reasoning) or a reply that is just the word. Anything
    else is UNKNOWN with ``parsed=False``: an unreadable reply is never guessed.
    """
    matches = list(_VERDICT.finditer(text))
    if matches:
        last = matches[-1]
        reasoning = text[: last.start()].strip() or None
        return Outcome(last.group(1).upper()), reasoning, True
    bare = _BARE.match(text.strip())
    if bare:
        return Outcome(bare.group(1).upper()), None, True
    snippet = " ".join(text.split())[:200]
    return Outcome.UNKNOWN, f"Unparseable judge reply: {snippet!r}", False
