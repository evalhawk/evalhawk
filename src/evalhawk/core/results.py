"""Estimate: the universal result value object for all statistical estimates.

An Estimate is a sealed receipt: the point estimate, its error range, sample size,
confidence level, the method used to compute it, and the fraction of unknown labels.
Every statistics function returns an Estimate.
"""

import math
from dataclasses import dataclass
from typing import Literal

# Decision type for version comparison results
Decision = Literal["BETTER", "WORSE", "INCONCLUSIVE"]


@dataclass(frozen=True, slots=True, kw_only=True)
class Estimate:
    """A statistical estimate with error interval.

    An Estimate is the universal type for results reported with an interval: pass
    rate, sensitivity, specificity, kappa, corrected rate, PPI, paired difference,
    or any other metric. It is frozen and uses slots for memory efficiency.

    Attributes:
        point: The point estimate (e.g., 0.82 for 82% pass rate). Can be any finite
            value; differences and kappa can be negative. No bounds enforced here.
        low: Lower bound of the confidence interval. Must be finite and <= high.
        high: Upper bound of the confidence interval. Must be finite and >= low.
        n: Number of items (e.g., test examples) the estimate describes. Must be
            >= 0. Interpretation depends on the method (e.g., sample size for Wilson,
            pairs for paired differences).
        method: Name of the method used to compute the estimate (e.g., "wilson",
            "cohen_kappa+bootstrap", "rogan_gladen+bootstrap"). Must be non-empty.
        confidence: Confidence level of the interval, as a fraction (e.g., 0.95 for
            95%). Must satisfy 0 < confidence < 1. Defaults to 0.95.
        unknown_rate: Fraction of labels marked unknown (e.g., 0.0 for no unknowns,
            0.125 for 12.5%). Must satisfy 0 <= unknown_rate <= 1. Defaults to 0.0.

    Invariants:
        - All numeric fields (point, low, high, confidence, unknown_rate) must be
          finite (not NaN or inf).
        - low <= high must hold.
        - n >= 0.
        - 0 < confidence < 1.
        - 0 <= unknown_rate <= 1.
        - method.strip() must be non-empty.
        - Point containment (low <= point <= high) is NOT enforced. Bootstrap
          methods may legitimately produce intervals that exclude the observed point.
        - Each method owns its bounds (e.g., Wilson guarantees [0, 1]; kappa might
          span [-1, 1]).
    """

    point: float
    low: float
    high: float
    n: int
    method: str
    confidence: float = 0.95
    unknown_rate: float = 0.0

    def __post_init__(self) -> None:
        """Validate field values in __post_init__.

        Checks are performed in order, raising ValueError with descriptive messages
        naming the field and showing the offending value.
        """
        # 1. Check finite: point, low, high, confidence, unknown_rate
        finite_fields = (
            ("point", self.point),
            ("low", self.low),
            ("high", self.high),
            ("confidence", self.confidence),
            ("unknown_rate", self.unknown_rate),
        )
        for name, value in finite_fields:
            if not math.isfinite(value):
                raise ValueError(f"Estimate: {name} must be finite, got {value!r}")

        # 2. Check low <= high
        if self.low > self.high:
            raise ValueError(
                f"Estimate: low must be <= high, got low={self.low!r}, high={self.high!r}"
            )

        # 3. Check n >= 0
        if self.n < 0:
            raise ValueError(f"Estimate: n must be >= 0, got {self.n!r}")

        # 4. Check 0 < confidence < 1
        if not (0 < self.confidence < 1):
            raise ValueError(
                f"Estimate: confidence must be strictly between 0 and 1, got {self.confidence!r}"
            )

        # 5. Check 0 <= unknown_rate <= 1
        if not (0 <= self.unknown_rate <= 1):
            raise ValueError(
                f"Estimate: unknown_rate must be between 0 and 1, got {self.unknown_rate!r}"
            )

        # 6. Check method is non-empty
        if not self.method.strip():
            raise ValueError(f"Estimate: method must be non-empty, got {self.method!r}")

    @property
    def width(self) -> float:
        """The width of the confidence interval (high - low)."""
        return self.high - self.low

    def __str__(self) -> str:
        """String representation: exact format specified in the card.

        Format: "point [low, high] (method, n=n, unknown=unknown_rate%)"
        where point, low, high are formatted to 3 decimal places and unknown_rate
        is shown as a percentage with 1 decimal place.
        """
        return (
            f"{self.point:.3f} [{self.low:.3f}, {self.high:.3f}] "
            f"({self.method}, n={self.n}, unknown={self.unknown_rate:.1%})"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Comparison:
    """Result of comparing two versions using paired data.

    A Comparison encapsulates the result of running v1 and v2 on the same inputs
    and comparing their binary outcomes using a paired test. It holds the estimated
    difference, its p-value, the disagreement counts, and a decision.

    Attributes:
        difference: The estimated difference (v2 - v1) as an Estimate from
            paired_bootstrap.
        p_value: The two-sided p-value from McNemar exact test, in [0, 1].
        b: Count of (v1=PASS, v2=FAIL) pairs. Must be >= 0.
        c: Count of (v1=FAIL, v2=PASS) pairs. Must be >= 0.
        decision: One of "BETTER" (v2 clearly better), "WORSE" (v1 clearly better),
            or "INCONCLUSIVE" (no significant difference).
    """

    difference: Estimate
    p_value: float
    b: int
    c: int
    decision: Decision

    def __post_init__(self) -> None:
        """Validate field values."""
        # Check p_value is finite and in [0, 1]
        if not math.isfinite(self.p_value):
            raise ValueError(f"Comparison: p_value must be finite, got {self.p_value!r}")
        if not (0 <= self.p_value <= 1):
            raise ValueError(f"Comparison: p_value must be in [0, 1], got {self.p_value!r}")

        # Check b >= 0
        if self.b < 0:
            raise ValueError(f"Comparison: b must be >= 0, got {self.b!r}")

        # Check c >= 0
        if self.c < 0:
            raise ValueError(f"Comparison: c must be >= 0, got {self.c!r}")

    def __str__(self) -> str:
        """String representation with signed differences.

        Format: "+0.040 [-0.010, +0.090] INCONCLUSIVE (p=0.210, b=12, c=30)"
        """
        point_str = f"{self.difference.point:+.3f}"
        low_str = f"{self.difference.low:+.3f}"
        high_str = f"{self.difference.high:+.3f}"

        return (
            f"{point_str} [{low_str}, {high_str}] {self.decision} "
            f"(p={self.p_value:.3f}, b={self.b}, c={self.c})"
        )

