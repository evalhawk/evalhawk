"""Read an OpenAI-compatible chat reply, with a clear error for thinking models.

Reasoning ("thinking") models such as Qwen 3.5 or DeepSeek-R1 spend part of ``max_tokens``
on hidden reasoning. If they run out before answering, the reply is empty and its
``finish_reason`` is ``"length"``; that is a configuration problem, not an unparseable answer.
"""

from typing import Any

from evalhawk.core.errors import CallError


def check_reasoning_effort(value: str | None) -> str | None:
    """Validate ``reasoning_effort`` at config time.

    Values are model-defined (commonly "none", "low", "medium", "high"; Ollama documents
    ``/api/show`` for each model's values), so any single word is accepted.
    """
    if value is not None and (not isinstance(value, str) or not value.strip() or " " in value):
        raise ValueError('reasoning_effort must be one word, for example "none" or "low"')
    return value


def reply_text(data: Any, *, base_url: str, max_tokens: int) -> tuple[dict[str, Any], str]:
    """The first choice and its text; empty, truncated replies raise a helpful CallError."""
    try:
        choice = data["choices"][0]
        text = str(choice["message"]["content"] or "")
    except (KeyError, IndexError, TypeError) as exc:
        raise CallError(f"{base_url}: unexpected chat response shape: {exc}") from exc
    if not text.strip() and choice.get("finish_reason") == "length":
        thought = bool(
            choice["message"].get("reasoning") or choice["message"].get("reasoning_content")
        )
        cause = "spent all of it thinking" if thought else "was cut off before answering"
        raise CallError(
            f"{base_url}: the model hit max_tokens={max_tokens} and {cause}; raise max_tokens "
            'or, for a thinking model, set reasoning_effort = "none"'
        )
    return choice, text
