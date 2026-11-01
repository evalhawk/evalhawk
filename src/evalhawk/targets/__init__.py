"""Target adapters: how EvalHawk calls the application being evaluated."""

from evalhawk.targets.callable import CallableTarget
from evalhawk.targets.http import HttpTarget
from evalhawk.targets.openai_compat import OpenAICompatibleTarget
from evalhawk.targets.recorded import RecordedTarget

__all__ = ["CallableTarget", "HttpTarget", "OpenAICompatibleTarget", "RecordedTarget"]
