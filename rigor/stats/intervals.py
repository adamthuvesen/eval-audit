"""Confidence intervals for binary success rates."""

from __future__ import annotations

from math import sqrt

from scipy.stats import norm


def wilson_interval(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float, float]:
    """Wilson score interval for a binary proportion.

    Returns (point_estimate, lower, upper) with bounds clipped to [0.0, 1.0].
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be in [0, n]")

    p = successes / n
    z = norm.ppf(1 - alpha / 2)
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z * sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom

    lo = max(0.0, center - margin)
    hi = min(1.0, center + margin)
    # Snap floating-point bleed at the edges to exact 0/1.
    if successes == 0:
        lo = 0.0
    if successes == n:
        hi = 1.0
    return p, lo, hi
