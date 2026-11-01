"""Judge adapters: prompt-based LLM judges, function judges and code checks."""

from evalhawk.judges.code import CHECKS, CodeCheckJudge
from evalhawk.judges.criteria import BUILTIN_CRITERIA, BuiltinCriterion, builtin_criterion
from evalhawk.judges.function import FunctionJudge
from evalhawk.judges.openai_compat import OpenAICompatibleJudge
from evalhawk.judges.prompt import Completion, PromptJudge

__all__ = [
    "BUILTIN_CRITERIA",
    "CHECKS",
    "BuiltinCriterion",
    "CodeCheckJudge",
    "Completion",
    "FunctionJudge",
    "OpenAICompatibleJudge",
    "PromptJudge",
    "builtin_criterion",
]
