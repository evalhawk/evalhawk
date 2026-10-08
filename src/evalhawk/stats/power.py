"""Power analysis for paired binary data (card S6).

Computes the number of paired examples (e.g., questions about the same document)
needed to detect a specified difference with given power.

References:
    - Miller, E. (2024). "Adding Error Bars to Evals: A Statistical Approach to
      Language Model Evaluations." arXiv:2411.00640.
"""

import math
from statistics import NormalDist


def required_n_paired(
    p_discordant: float,
    delta: float,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
) -> int:
    """Required sample size for detecting difference in paired data.

    Given the probability p_discordant of discordant pairs and a target
    difference Δ (in percentage points), compute the number of paired
    examples needed to detect the difference with specified power.

    Formula:
        N = ceil((z_{1−α/2} + z_{power})² · (p_disc − Δ²) / Δ²)

    Args:
        p_discordant: Probability of discordant pairs. Must be in (0, 1].
        delta: Target difference in percentage points. Must be non-zero
            and satisfy Δ² < p_discordant.
        alpha: Significance level (Type I error). Must be in (0, 1).
            Defaults to 0.05.
        power: Statistical power (1 - Type II error). Must be in (0, 1).
            Defaults to 0.8.

    Returns:
        The required sample size (number of pairs) as an int, rounded up.

    Raises:
        ValueError: If p_discordant not in (0, 1], delta == 0, Δ² >= p_disc,
            or alpha/power not in (0, 1).

    References:
        - Miller, E. (2024). "Adding Error Bars to Evals: A Statistical Approach
          to Language Model Evaluations." arXiv:2411.00640.
    """
    # Validate p_discordant
    if not (0 < p_discordant <= 1):
        raise ValueError(f"p_discordant must be in (0, 1], got {p_discordant!r}")

    # Validate delta
    if delta == 0:
        raise ValueError(f"delta must be non-zero, got {delta!r}")

    # Validate Δ² < p_discordant
    delta_sq = delta**2
    if delta_sq >= p_discordant:
        raise ValueError(
            f"Δ² must be < p_discordant, got Δ²={delta_sq!r}, "
            f"p_discordant={p_discordant!r}"
        )

    # Validate alpha
    if not (0 < alpha < 1):
        raise ValueError(f"alpha must be in (0, 1), got {alpha!r}")

    # Validate power
    if not (0 < power < 1):
        raise ValueError(f"power must be in (0, 1), got {power!r}")

    # z_{1-alpha/2} (two-sided) and z_{power} (one-sided) are different quantiles
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1 - alpha / 2)
    z_power_val = normal.inv_cdf(power)

    # Compute numerator
    numerator = (z_alpha + z_power_val) ** 2 * (p_discordant - delta_sq)

    # Compute denominator
    denominator = delta_sq

    # Compute n
    n_exact = numerator / denominator

    # Round up
    n_required = math.ceil(n_exact)

    return n_required
