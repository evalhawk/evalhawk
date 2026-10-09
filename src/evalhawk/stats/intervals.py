"""Confidence intervals for proportions.

Implements the Wilson score interval (Wilson, 1927), which is superior to the
Wald interval for extreme proportions and always stays within [0, 1].
"""

import math
from typing import SupportsIndex

from evalhawk.core.results import Estimate
from evalhawk.stats._checks import as_count, check_confidence, z_value


def wilson_interval(k: SupportsIndex, n: SupportsIndex, *, confidence: float = 0.95) -> Estimate:
    """Compute a Wilson score confidence interval for a proportion.

    The Wilson interval is more accurate than Wald for extreme proportions and
    is guaranteed to stay within [0, 1]. It is the recommended method for
    binomial confidence intervals (Brown, Cai & DasGupta, 2001).

    The formula is:
        p̂ = k / n
        z = z_score(confidence)
        denom = 1 + z² / n
        centre = (p̂ + z² / (2n)) / denom
        margin = (z / denom) × √(p̂(1 - p̂) / n + z² / (4n²))
        low = max(0, centre - margin)
        high = min(1, centre + margin)

    Args:
        k: Number of successes (a non-negative Python or NumPy integer).
        n: Total number of trials (a positive Python or NumPy integer).
        confidence: Confidence level (e.g., 0.95 for 95%). Must be in (0, 1).
            Defaults to 0.95.

    Returns:
        An Estimate with the point estimate, interval bounds, and metadata.

    Raises:
        ValueError: If k or n is a bool or not integer-like, or if k, n, or confidence are
            out of valid ranges.

    References:
        - Wilson, E. B. (1927). "Probable inference, the law of succession, and
          statistical inference." Journal of the American Statistical Association,
          22(158), 209–212.
        - Brown, L. D., Cai, T. T., & DasGupta, A. (2001). "Interval estimation
          for a binomial proportion." Statistical Science, 16(2), 101–133.

    Example:
        >>> est = wilson_interval(82, 100)
        >>> print(est)
        0.820 [0.733, 0.883] (wilson, n=100, unknown=0.0%)
    """
    # Validate k, n are integer-like (Python or NumPy ints) but not bool
    k = as_count("k", k)
    n = as_count("n", n)

    # Validate k and n ranges
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n!r}")
    if k < 0 or k > n:
        raise ValueError(f"k must be in [0, n], got k={k!r}, n={n!r}")

    # Validate confidence
    check_confidence(confidence)

    # Compute point estimate
    p = k / n

    # Compute z-score
    z = z_value(confidence)
    z_sq = z * z

    # Compute denominator
    denom = 1 + z_sq / n

    # Compute centre
    centre = (p + z_sq / (2 * n)) / denom

    # Compute half-width (margin of error)
    # half = (z / denom) * sqrt(p(1-p)/n + z²/(4n²))
    variance_term = p * (1 - p) / n + z_sq / (4 * n * n)
    half = (z / denom) * math.sqrt(variance_term)

    # Bounds are exactly 0 at k = 0 and 1 at k = n; float noise must not push them past the point
    low = 0.0 if k == 0 else max(0.0, centre - half)
    high = 1.0 if k == n else min(1.0, centre + half)

    return Estimate(
        point=p,
        low=low,
        high=high,
        n=n,
        method="wilson",
        confidence=confidence,
    )
