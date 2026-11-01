"""Prompt-based LLM judges: one template, strict parsing, a stable judge identity.

:class:`PromptJudge` is the optional helper base class from ADR-0004 (template method):
it renders the prompt, calls :meth:`PromptJudge.complete`, parses the verdict and builds
the :class:`~evalhawk.core.models.Verdict`. An LLM adapter only implements ``complete``.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar, Literal

from evalhawk.core.ids import content_id, normalize_text
from evalhawk.core.models import Criterion, Example, Outcome, Trace, Verdict
from evalhawk.judges.criteria import BUILTIN_CRITERIA
from evalhawk.judges.parsing import parse_verdict

Mode = Literal["reason_then_verdict", "verdict_only"]

SYSTEM_PROMPT = (
    "You are a careful, impartial evaluator of AI assistant answers. You judge exactly one "
    "yes/no question about one answer. Base your decision only on the material provided. "
    "Do not reward length, confidence or style unless the question asks about them."
)

_INSTRUCTIONS: dict[str, str] = {
    "reason_then_verdict": (
        "Explain your reasoning briefly, then end with one final line that is exactly "
        "'VERDICT: PASS', 'VERDICT: FAIL' or 'VERDICT: UNKNOWN'. PASS means the answer to "
        "the question above is yes. Use UNKNOWN only if the material is insufficient to decide."
    ),
    "verdict_only": (
        "Reply with exactly one word: PASS, FAIL or UNKNOWN. PASS means the answer to the "
        "question above is yes. Use UNKNOWN only if the material is insufficient to decide."
    ),
}

TEMPLATE_VERSION = "prompt-v1"


@dataclass(frozen=True, slots=True)
class Completion:
    """What a model call returned: the text and, optionally, P(PASS) and the cost."""

    text: str
    probability: float | None = None
    cost_usd: float = 0.0
    latency_ms: float = 0.0


def _as_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def render_messages(
    example: Example,
    trace: Trace,
    criterion: Criterion,
    *,
    mode: Mode = "reason_then_verdict",
    guidance: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """Build the chat messages for one judgment (system prompt + one user message)."""
    rules = (
        guidance if guidance is not None else {k: v.guidance for k, v in BUILTIN_CRITERIA.items()}
    )
    parts = [f"## Question to decide\n{criterion.question}"]
    if criterion.name in rules:
        parts.append(f"## How to judge\n{rules[criterion.name]}")
    parts.append(f"## Input given to the assistant\n{_as_text(example.input)}")
    if example.reference is not None:
        parts.append(f"## Reference answer\n{_as_text(example.reference)}")
    if trace.contexts is not None:
        numbered = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(trace.contexts, 1))
        parts.append(f"## Retrieved context\n{numbered or '(no context was retrieved)'}")
    parts.append(f"## Answer to evaluate\n{trace.output}")
    parts.append(f"## Your reply\n{_INSTRUCTIONS[mode]}")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


class PromptJudge:
    """Optional base class for LLM judges; subclasses implement :meth:`complete`.

    The ``judge_id`` hashes everything that changes the judge's behaviour: adapter, model,
    mode, sampling parameters, the prompt template and the guidance texts. Change any of
    them and you get a new judge, whose calibration must be measured again.
    """

    adapter: ClassVar[str] = "prompt"

    def __init__(
        self,
        *,
        model: str,
        mode: Mode = "reason_then_verdict",
        params: Mapping[str, object] | None = None,
        guidance: Mapping[str, str] | None = None,
    ) -> None:
        if mode not in _INSTRUCTIONS:
            raise ValueError(f"mode must be one of {sorted(_INSTRUCTIONS)}, got {mode!r}")
        self.model = model
        self.mode: Mode = mode
        self.params = dict(params or {})
        self.guidance = dict(
            guidance
            if guidance is not None
            else {k: v.guidance for k, v in BUILTIN_CRITERIA.items()}
        )

    def identity(self) -> object:
        """Everything that defines this judge's behaviour (never secrets)."""
        return [
            "judge-v1",
            self.adapter,
            self.model,
            self.mode,
            self.params,
            TEMPLATE_VERSION,
            normalize_text(SYSTEM_PROMPT + "\n" + _INSTRUCTIONS[self.mode]),
            {name: normalize_text(text) for name, text in sorted(self.guidance.items())},
        ]

    @property
    def judge_id(self) -> str:
        return content_id(self.identity())

    async def complete(self, messages: list[dict[str, str]]) -> Completion:
        """Call the model. Subclasses must implement this."""
        raise NotImplementedError

    async def judge(self, example: Example, trace: Trace, criterion: Criterion) -> Verdict:
        """Render, call, parse; an unreadable reply becomes UNKNOWN with an explanation."""
        messages = render_messages(
            example, trace, criterion, mode=self.mode, guidance=self.guidance
        )
        completion = await self.complete(messages)
        outcome, reasoning, _ = parse_verdict(completion.text)
        probability = completion.probability if outcome is not Outcome.UNKNOWN else None
        return Verdict(
            trace_id=trace.id,
            criterion_id=criterion.id,
            judge_id=self.judge_id,
            outcome=outcome,
            probability=probability,
            reasoning=reasoning,
            cost_usd=completion.cost_usd,
            latency_ms=completion.latency_ms,
        )
