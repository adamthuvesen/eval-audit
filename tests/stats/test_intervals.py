"""Acceptance tests for Wilson score interval."""

from __future__ import annotations

from math import isclose


def test_wilson__known_reference_values() -> None:
    """WHEN wilson_interval(54, 100, 0.05) is called,
    THEN the returned tuple matches scipy.stats reference values within 1e-6.
    """
    from scipy.stats import binomtest

    from rigor.stats import wilson_interval

    point, lo, hi = wilson_interval(54, 100, 0.05)
    ref = binomtest(54, 100).proportion_ci(method="wilson", confidence_level=0.95)

    assert isclose(point, 0.54, abs_tol=1e-12)
    assert isclose(lo, ref.low, abs_tol=1e-6)
    assert isclose(hi, ref.high, abs_tol=1e-6)


def test_wilson__edge_case_at_zero_successes() -> None:
    """WHEN wilson_interval(0, 50, 0.05) is called,
    THEN the lower bound equals 0.0 and the upper bound is positive and < 0.1.
    """
    from rigor.stats import wilson_interval

    point, lo, hi = wilson_interval(0, 50, 0.05)
    assert point == 0.0
    assert lo == 0.0
    assert 0.0 < hi < 0.1
