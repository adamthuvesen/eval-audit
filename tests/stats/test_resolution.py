"""Unit tests for resolution planning math."""

from __future__ import annotations

import pytest

from eval_audit.stats.resolution import (
    ResolutionEstimate,
    estimate_required_paired_tasks,
)


def test_resolution__ci_already_inside_mde_returns_zero_additional() -> None:
    """When current_ci_half_width <= target_mde, no additional tasks are needed."""
    est = estimate_required_paired_tasks(
        current_n_paired=100,
        current_ci_half_width=0.02,
        target_mde=0.03,
    )
    assert est == ResolutionEstimate(
        additional_tasks=0,
        total_tasks=100,
        assumption="variance-fixed scaling",
    )


def test_resolution__doubling_precision_requires_roughly_4x_n() -> None:
    """h_target = h_current/2 means N_required ≈ 4 × N_current."""
    est = estimate_required_paired_tasks(
        current_n_paired=100,
        current_ci_half_width=0.06,
        target_mde=0.03,
    )
    assert est.total_tasks == 400
    assert est.additional_tasks == 300


def test_resolution__ceiling_rounding_never_under_promises() -> None:
    """100 × (0.05/0.04)^2 = 156.25, ceiling-rounded to 157."""
    est = estimate_required_paired_tasks(
        current_n_paired=100,
        current_ci_half_width=0.05,
        target_mde=0.04,
    )
    assert est.total_tasks == 157
    assert est.additional_tasks == 57


def test_resolution__non_positive_current_n_paired_raises() -> None:
    with pytest.raises(ValueError) as exc_info:
        estimate_required_paired_tasks(
            current_n_paired=0,
            current_ci_half_width=0.05,
            target_mde=0.03,
        )
    assert "current_n_paired" in str(exc_info.value)


def test_resolution__non_positive_target_mde_raises() -> None:
    with pytest.raises(ValueError) as exc_info:
        estimate_required_paired_tasks(
            current_n_paired=100,
            current_ci_half_width=0.05,
            target_mde=0.0,
        )
    assert "target_mde" in str(exc_info.value)


def test_resolution__negative_ci_half_width_raises() -> None:
    with pytest.raises(ValueError) as exc_info:
        estimate_required_paired_tasks(
            current_n_paired=100,
            current_ci_half_width=-0.01,
            target_mde=0.03,
        )
    assert "current_ci_half_width" in str(exc_info.value)


def test_resolution__assumption_field_pinned_to_variance_fixed_scaling() -> None:
    """The assumption string identifies the model used. Pin it explicitly."""
    inside = estimate_required_paired_tasks(100, 0.02, 0.03)
    outside = estimate_required_paired_tasks(100, 0.06, 0.03)
    assert inside.assumption == "variance-fixed scaling"
    assert outside.assumption == "variance-fixed scaling"
