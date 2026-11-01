"""``evalhawk.toml``: the typed configuration for live evaluations.

The file is validated when it's loaded, so mistakes (an unknown judge, a RAG check on a
non-RAG evaluation, a missing dataset) fail in a second, before any paid call. ``${VAR}``
placeholders are *not* expanded here: they are expanded only when adapters are built
(:func:`expand_env`), so the run's saved config snapshot never contains a secret.
"""

import os
import re
import tomllib
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from evalhawk.core.errors import ConfigError

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

CODE_JUDGE = "code"
"""The judge name that maps a ``check`` criterion to its code check."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _OpenSection(BaseModel):
    """A section whose extra keys are adapter options."""

    model_config = ConfigDict(extra="allow")

    def options(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class ProjectConfig(_Section):
    name: str = "evalhawk-project"
    store: Path = Path(".evalhawk/eval.db")


class SplitsConfig(_Section):
    salt: str = "v1"
    ratios: tuple[float, float, float] = (0.2, 0.4, 0.4)
    by: Literal["group_id", "example_id"] = "group_id"


class TargetConfig(_OpenSection):
    type: Literal["callable", "http", "openai_compatible", "recorded"]


class JudgeConfig(_OpenSection):
    type: str


class CriterionConfig(_Section):
    """Exactly one of ``question`` (custom), ``template`` (built-in) or ``check`` (code)."""

    name: str
    question: str | None = None
    template: str | None = None
    check: dict[str, Any] | None = None

    @model_validator(mode="after")
    def exactly_one_kind(self) -> Self:
        given = [k for k in ("question", "template", "check") if getattr(self, k) is not None]
        if len(given) != 1:
            raise ValueError(
                f"criterion {self.name!r}: set exactly one of question, template or check "
                f"(got {', '.join(given) or 'none'})"
            )
        if self.check is not None and "type" not in self.check:
            raise ValueError(f"criterion {self.name!r}: check needs a 'type', e.g. max_words")
        return self


class EvaluationConfig(_Section):
    dataset: Path
    kind: Literal["single_turn", "rag"] = "single_turn"
    criteria: dict[str, str | list[str]]
    repeats: int = Field(default=1, ge=1)
    estimator: Literal["rogan_gladen", "ppi"] = "ppi"

    def pairs(self) -> list[tuple[str, str]]:
        """(criterion name, judge name) pairs; a criterion may have several judges."""
        out: list[tuple[str, str]] = []
        for criterion, judges in self.criteria.items():
            for judge in [judges] if isinstance(judges, str) else judges:
                out.append((criterion, judge))
        return out


class RunnerConfig(_Section):
    max_concurrency: int = Field(default=8, ge=1)
    retries: int = Field(default=3, ge=0)
    base_delay: float = Field(default=1.0, ge=0)
    max_delay: float = Field(default=30.0, ge=0)
    timeout: float = Field(default=120.0, gt=0)
    max_cost_usd: float | None = Field(default=None, ge=0)
    seed: int = 0


class Config(_Section):
    version: Literal[1] = 1
    project: ProjectConfig = ProjectConfig()
    target: TargetConfig | None = None
    splits: SplitsConfig = SplitsConfig()
    criteria: list[CriterionConfig] = Field(default_factory=list[CriterionConfig])
    judges: dict[str, JudgeConfig] = Field(default_factory=dict[str, JudgeConfig])
    evaluations: dict[str, EvaluationConfig] = Field(default_factory=dict[str, EvaluationConfig])
    runner: RunnerConfig = RunnerConfig()
    base_dir: Path = Path(".")

    @model_validator(mode="after")
    def references_resolve(self) -> Self:
        names = [c.name for c in self.criteria]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"duplicate criterion names: {', '.join(sorted(duplicates))}")
        by_name = {c.name: c for c in self.criteria}
        for evaluation_name, evaluation in self.evaluations.items():
            for criterion_name, judge_name in evaluation.pairs():
                criterion = by_name.get(criterion_name)
                where = f"evaluation {evaluation_name!r}"
                if criterion is None:
                    raise ValueError(f"{where}: unknown criterion {criterion_name!r}")
                if criterion.check is not None and judge_name != CODE_JUDGE:
                    raise ValueError(
                        f"{where}: {criterion_name!r} is a code check, so its judge must be "
                        f"{CODE_JUDGE!r}"
                    )
                if criterion.check is None and judge_name == CODE_JUDGE:
                    raise ValueError(
                        f"{where}: {criterion_name!r} needs an LLM or function judge, not "
                        f"{CODE_JUDGE!r} (only check criteria use code)"
                    )
                if judge_name != CODE_JUDGE and judge_name not in self.judges:
                    raise ValueError(f"{where}: unknown judge {judge_name!r}")
        return self

    def evaluation(self, name: str | None) -> tuple[str, EvaluationConfig]:
        """Select an evaluation by name, or the only one."""
        if name is None:
            if len(self.evaluations) != 1:
                raise ConfigError(
                    f"choose an evaluation with --evaluation: {', '.join(self.evaluations)}"
                )
            name = next(iter(self.evaluations))
        if name not in self.evaluations:
            raise ConfigError(
                f"no evaluation {name!r}; available: {', '.join(self.evaluations) or 'none'}"
            )
        return name, self.evaluations[name]

    def resolve(self, path: Path) -> Path:
        """Paths in the config are relative to the config file's folder."""
        return path if path.is_absolute() else self.base_dir / path


def load_config(path: str | Path) -> Config:
    """Read and validate ``evalhawk.toml``; errors name the file and the problem."""
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{path}: not found; create one with `evalhawk init`") from None
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"{path}: cannot read: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc
    try:
        return Config.model_validate({**raw, "base_dir": path.resolve().parent})
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in error['loc']) or 'config'}: {error['msg']}"
            for error in exc.errors()
        )
        raise ConfigError(f"{path}: {problems}") from exc


def expand_env(value: Any) -> Any:
    """Replace ``${VAR}`` with the environment variable's value, recursively."""
    if isinstance(value, str):

        def substitute(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise ConfigError(f"environment variable {name} is not set (used as ${{{name}}})")
            return os.environ[name]

        return _ENV.sub(substitute, value)
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    return value
