"""Resolution planning: estimate paired-task N for a target CI half-width.

This is intentionally simple math, not formal power analysis. The
variance-fixed scaling assumption (CI half-width ∝ 1/sqrt(N) for fixed
underlying variance) is exposed in the rendered output and the
``ResolutionEstimate.assumption`` field so consumers can see the model used.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

_ASSUMPTION = "variance-fixed scaling"


@dataclass(frozen=True)
class ResolutionEstimate:
    additional_tasks: int
    total_tasks: int
    assumption: str


def estimate_required_paired_tasks(
    current_n_paired: int,
    current_ci_half_width: float,
    target_mde: float,
) -> ResolutionEstimate:
    """Estimate paired-task N needed to bring CI half-width <= target_mde.

    Uses the variance-fixed scaling approximation:
    ``N_required ≈ N_current × (h_current / h_target)^2``, ceiling-rounded.

    Returns ``additional_tasks=0`` when CI half-width is already at or below
    the declared MDE.
    """
    if current_n_paired <= 0:
        raise ValueError(
            f"current_n_paired must be positive (got {current_n_paired})"
        )
    if target_mde <= 0:
        raise ValueError(f"target_mde must be positive (got {target_mde})")
    if current_ci_half_width < 0:
        raise ValueError(
            f"current_ci_half_width must be non-negative "
            f"(got {current_ci_half_width})"
        )

    if current_ci_half_width <= target_mde:
        return ResolutionEstimate(
            additional_tasks=0,
            total_tasks=current_n_paired,
            assumption=_ASSUMPTION,
        )

    n_required = ceil(current_n_paired * (current_ci_half_width / target_mde) ** 2)
    additional = max(0, n_required - current_n_paired)
    total = max(current_n_paired, n_required)
    return ResolutionEstimate(
        additional_tasks=additional,
        total_tasks=total,
        assumption=_ASSUMPTION,
    )
