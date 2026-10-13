"""Deterministic group-aware assignment, scoped to immutable split configurations."""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import model_validator

from evalhawk.core.ids import content_id
from evalhawk.core.models import Example, IdentifiedRecord, Identifier, Split


def _ratios(ratios: tuple[float, float, float]) -> None:
    if len(ratios) != 3 or any(not math.isfinite(value) or value < 0 for value in ratios):
        raise ValueError("ratios must contain three finite non-negative values")
    if not math.isclose(sum(ratios), 1, rel_tol=0, abs_tol=1e-12):
        raise ValueError("ratios must sum to 1")


def assign_split(
    key: str, *, salt: str, ratios: tuple[float, float, float] = (0.2, 0.4, 0.4)
) -> Split:
    """Hash a structured salt/key pair; ratios are approximate over distinct keys."""
    _ratios(ratios)
    if not key or not salt:
        raise ValueError("key and salt must be non-empty")
    position = int(content_id(["split-v1", salt, key])[:8], 16) / 16**8
    total = sum(ratios)
    boundary = 0.0
    for pile, ratio in zip(Split, ratios, strict=True):
        boundary += ratio / total
        if ratio > 0 and position < boundary:
            return pile
    return next(
        pile for pile, ratio in reversed(tuple(zip(Split, ratios, strict=True))) if ratio > 0
    )


def split_key(example: Example, *, by: Literal["group_id", "example_id"] = "group_id") -> str:
    """Namespace group and example keys so a user group cannot collide with an ID."""
    if by == "group_id" and example.group_id is not None:
        return content_id(["group", example.group_id])
    return content_id(["example", example.id])


class SplitSet(IdentifiedRecord):
    """One immutable configuration; new sets do not erase prior exposure to data."""

    salt: Identifier = "v1"
    ratios: tuple[float, float, float] = (0.2, 0.4, 0.4)
    by: Literal["group_id", "example_id"] = "group_id"

    @model_validator(mode="after")
    def validate_ratios(self) -> Self:
        _ratios(self.ratios)
        return self

    def identity(self) -> object:
        return ["split-set-v1", self.salt, self.ratios, self.by]

    def assign(self, example: Example) -> Split:
        """Assign without depending on import order or other examples."""
        return assign_split(split_key(example, by=self.by), salt=self.salt, ratios=self.ratios)


@dataclass(frozen=True, slots=True)
class SplitDiagnostics:
    """Actual counts and heuristic warnings, not confidence-interval guarantees."""

    counts: dict[Split, int]
    tag_counts: dict[str, dict[Split, int]]
    distinct_keys: int
    warnings: tuple[str, ...]


def diagnose_splits(
    config: SplitSet,
    examples: Iterable[Example],
    *,
    minimum_per_pile: int = 10,
    minimum_groups: int = 20,
    maximum_group_fraction: float = 0.1,
) -> SplitDiagnostics:
    """Summarize a complete input snapshot; thresholds are configurable heuristics."""
    if minimum_per_pile < 0 or minimum_groups < 0:
        raise ValueError("minimum counts must be non-negative")
    if not math.isfinite(maximum_group_fraction) or not 0 < maximum_group_fraction <= 1:
        raise ValueError("maximum_group_fraction must be in (0, 1]")
    unique = {example.id: example for example in examples}
    counts = dict.fromkeys(Split, 0)
    tags: dict[str, dict[Split, int]] = {}
    keys: dict[str, int] = {}
    grouped = False
    for example in unique.values():
        pile = config.assign(example)
        counts[pile] += 1
        key = split_key(example, by=config.by)
        keys[key] = keys.get(key, 0) + 1
        grouped |= example.group_id is not None
        for tag in set(example.tags):
            tags.setdefault(tag, dict.fromkeys(Split, 0))[pile] += 1
    warnings: list[str] = []
    active = [pile for pile, ratio in zip(Split, config.ratios, strict=True) if ratio > 0]
    for pile in active:
        if counts[pile] < minimum_per_pile:
            warnings.append(
                f"{pile.value}: only {counts[pile]} examples; estimates may be uncertain"
            )
    for tag, tag_counts in sorted(tags.items()):
        for pile in active:
            if tag_counts[pile] < minimum_per_pile:
                warnings.append(f"tag {tag}, {pile.value}: only {tag_counts[pile]} examples")
    if grouped and len(keys) < minimum_groups:
        warnings.append(
            f"only {len(keys)} distinct groups/ungrouped examples; "
            "clustered inference may be unstable"
        )
    if grouped and unique and max(keys.values()) / len(unique) > maximum_group_fraction:
        warnings.append("one dependence group dominates the dataset; pile ratios may be lopsided")
    return SplitDiagnostics(counts, tags, len(keys), tuple(warnings))
