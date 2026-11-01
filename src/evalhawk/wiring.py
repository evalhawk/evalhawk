"""Construct concrete adapters at the application boundary (the composition root).

This is the only module that knows which judge, target, source and store classes exist.
Services and the runner receive objects that satisfy the ``core.protocols`` ports.
Third-party judges register through the ``evalhawk.judges`` entry-point group and are
then usable from config as ``type = "<name>"``.
"""

import importlib
import sys
from collections.abc import Callable
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from evalhawk.config import (
    CODE_JUDGE,
    Config,
    CriterionConfig,
    JudgeConfig,
    TargetConfig,
    expand_env,
)
from evalhawk.core.errors import ConfigError, DataError
from evalhawk.core.models import Criterion, Example, Run, TargetOutput
from evalhawk.core.protocols import Judge, Target
from evalhawk.judges.code import CodeCheckJudge
from evalhawk.judges.criteria import BUILTIN_CRITERIA
from evalhawk.judges.function import FunctionJudge
from evalhawk.judges.openai_compat import OpenAICompatibleJudge
from evalhawk.runner.executor import JudgeSpec
from evalhawk.sources.csv import CSVSource
from evalhawk.sources.jsonl import JSONLSource
from evalhawk.sources.verdicts import VerdictSource
from evalhawk.storage.sqlite import SQLiteStore
from evalhawk.targets.callable import CallableTarget
from evalhawk.targets.http import HttpTarget
from evalhawk.targets.openai_compat import OpenAICompatibleTarget
from evalhawk.targets.recorded import RecordedTarget


def open_store(path: Path) -> SQLiteStore:
    """Open the user's explicitly selected evaluation database."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return SQLiteStore(path)


def recorded_source(path: Path, *, run: Run, criterion: Criterion, judge_id: str) -> VerdictSource:
    """Create a file adapter without exposing it to services."""
    return VerdictSource(path, run=run, criterion=criterion, judge_id=judge_id)


def resolve_callable(spec: str, *, base_dir: Path) -> Callable[..., Any]:
    """Import ``"package.module:function"``; the config's folder is importable."""
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise ConfigError(f"callable must look like 'module:function', got {spec!r}")
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    try:
        target: Any = importlib.import_module(module_name)
        for part in attribute.split("."):
            target = getattr(target, part)
    except (ImportError, AttributeError) as exc:
        raise ConfigError(f"cannot import {spec!r}: {exc}") from exc
    if not callable(target):
        raise ConfigError(f"{spec!r} is not callable")
    return target


def load_rows(path: Path) -> list[tuple[Example, TargetOutput | None]]:
    """Read a dataset (``.jsonl`` or ``.csv``) into memory."""
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return list(JSONLSource(path).load())
    if suffix == ".csv":
        return list(CSVSource(path).load())
    raise DataError(f"{path}: dataset must be .jsonl or .csv")


def build_target(
    config: TargetConfig, *, base_dir: Path, rows: list[tuple[Example, TargetOutput | None]]
) -> Target:
    """Build the configured target; ``${VAR}`` placeholders are expanded here."""
    options = expand_env(config.options())
    try:
        if config.type == "callable":
            fn = resolve_callable(str(options.pop("callable", "")), base_dir=base_dir)
            return CallableTarget(fn, **options)
        if config.type == "http":
            return HttpTarget(**options)
        if config.type == "openai_compatible":
            return OpenAICompatibleTarget(**options)
        return RecordedTarget.from_rows(rows)
    except TypeError as exc:
        raise ConfigError(f"[target] type={config.type!r}: {exc}") from exc


def _plugin_judges() -> dict[str, Any]:
    return {entry.name: entry for entry in entry_points(group="evalhawk.judges")}


def build_judge(name: str, config: JudgeConfig, *, base_dir: Path) -> Judge:
    """Build ``[judges.<name>]``; ``${VAR}`` placeholders are expanded here."""
    options = expand_env(config.options())
    try:
        if config.type == "openai_compatible":
            return OpenAICompatibleJudge(**options)
        if config.type == "function":
            fn = resolve_callable(str(options.pop("callable", "")), base_dir=base_dir)
            return FunctionJudge(fn, name=str(options.pop("name", name)), **options)
        plugins = _plugin_judges()
        if config.type in plugins:
            return plugins[config.type].load()(**options)
    except TypeError as exc:
        raise ConfigError(f"[judges.{name}] type={config.type!r}: {exc}") from exc
    known = ["openai_compatible", "function", *sorted(plugins)]
    raise ConfigError(f"[judges.{name}]: unknown type {config.type!r}; known: {', '.join(known)}")


def build_criterion(config: CriterionConfig) -> Criterion:
    """A custom question, a built-in template, or a code check (whose question names it)."""
    if config.template is not None:
        if config.template not in BUILTIN_CRITERIA:
            available = ", ".join(sorted(BUILTIN_CRITERIA))
            raise ConfigError(
                f"criterion {config.name!r}: unknown template {config.template!r}; "
                f"available: {available}"
            )
        return Criterion(name=config.name, question=BUILTIN_CRITERIA[config.template].question)
    if config.check is not None:
        options = ", ".join(f"{k}={v!r}" for k, v in config.check.items() if k != "type")
        return Criterion(
            name=config.name,
            question=f"Does the output pass the code check {config.check['type']}({options})?",
        )
    return Criterion(name=config.name, question=str(config.question))


def build_specs(config: Config, evaluation: str) -> tuple[list[JudgeSpec], bool]:
    """Every (criterion, judge) of an evaluation, and whether traces need contexts."""
    _, chosen = config.evaluation(evaluation)
    criteria = {c.name: c for c in config.criteria}
    judges: dict[str, Judge] = {}
    specs: list[JudgeSpec] = []
    for criterion_name, judge_name in chosen.pairs():
        criterion_config = criteria[criterion_name]
        if criterion_config.template is not None:
            builtin = BUILTIN_CRITERIA.get(criterion_config.template)
            if builtin is not None and builtin.needs_contexts and chosen.kind != "rag":
                raise ConfigError(
                    f"criterion {criterion_name!r} uses template {criterion_config.template!r}, "
                    'which needs retrieved contexts: set kind = "rag" on the evaluation'
                )
        if judge_name == CODE_JUDGE:
            check = dict(criterion_config.check or {})
            try:
                judge: Judge = CodeCheckJudge(str(check.pop("type")), **check)
            except ValueError as exc:
                raise ConfigError(f"criterion {criterion_name!r}: {exc}") from exc
        else:
            if judge_name not in judges:
                judges[judge_name] = build_judge(
                    judge_name, config.judges[judge_name], base_dir=config.base_dir
                )
            judge = judges[judge_name]
        specs.append(JudgeSpec(build_criterion(criterion_config), judge))
    return specs, chosen.kind == "rag"


def needs_reference(config: Config, evaluation: str) -> list[str]:
    """Names of the evaluation's criteria that need a reference answer."""
    _, chosen = config.evaluation(evaluation)
    by_name = {c.name: c for c in config.criteria}
    names: list[str] = []
    for criterion_name, _ in chosen.pairs():
        template = by_name[criterion_name].template
        if template and BUILTIN_CRITERIA[template].needs_reference and criterion_name not in names:
            names.append(criterion_name)
    return names
