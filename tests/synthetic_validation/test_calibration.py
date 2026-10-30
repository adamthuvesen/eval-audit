"""Finite calibration checks across independent, unselected paired-task draws."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
import pytest
from scipy.stats import binom

from eval_audit.schema import AgentRef, Claim
from eval_audit.stats import analyze
from eval_audit.stats.sensitivity import recompute_scenario
from tests.stats.test_analyze import _row, _stub_study

# These bounds precede the simulation. They are smoke-test acceptance bounds,
# not confidence guarantees for every benchmark distribution.
_DRAWS = 128
_TASKS = 120
_REPLICATES = 3
_ALPHA = 0.05
_TAIL = 0.001
_BOOTSTRAPS = 1_000
_SEED = 20261105
_MAX_NULL_REJECTIONS = int(binom.ppf(1 - _TAIL, _DRAWS, _ALPHA))
_MIN_COVERED = int(binom.ppf(_TAIL, _DRAWS, 1 - _ALPHA))
_MIN_DETECTED = int(binom.ppf(_TAIL, _DRAWS, 0.90))


@dataclass(frozen=True)
class CalibrationCounts:
    null_family_rejections: int
    null_covered: int
    excluded_null_family_rejections: int
    excluded_null_covered: int
    alternative_detected: int
    alternative_covered: int


def _draw(rng: np.random.Generator, *, alternative: bool):
    study = _stub_study("t", "c", "h")
    study = study.model_copy(
        update={
            "agents": [AgentRef(id=a) for a in ("t", "c", "u")],
            "claims": [
                study.claims[0],
                Claim(
                    id="c2", text="u beats c", treatment="u", control="c", outcome="success_rate"
                ),
            ],
            "design": study.design.model_copy(update={"observed_runs_per_agent": _REPLICATES}),
        }
    )
    difficulty = rng.choice([0.2, 0.8], size=_TASKS)
    if alternative:
        difficulty = rng.choice([0.2, 0.6], size=_TASKS)
    rows = []
    for agent in ("t", "c", "u"):
        probability = difficulty.copy()
        if alternative:
            probability += 0.15 if agent == "t" else -0.15
        outcomes = rng.random((_TASKS, _REPLICATES)) < probability[:, None]
        errored = np.zeros(_TASKS, dtype=bool) if alternative else rng.random(_TASKS) < 0.1
        for task in range(_TASKS):
            for replicate in range(_REPLICATES):
                row = _row(agent, f"task-{task:03d}", "h")
                row["run_id"] = f"run-{agent}-{replicate}"
                row["seed"] = replicate
                row["success"] = None if errored[task] else bool(outcomes[task, replicate])
                row["partial_credit"] = row["success"]
                row["outcome_status"] = "errored" if errored[task] else "graded"
                rows.append(row)
    return study, pl.DataFrame(rows)


@pytest.fixture(scope="module")
def calibration_counts() -> CalibrationCounts:
    rng = np.random.default_rng(_SEED)
    null_rejected = null_covered = excluded_rejected = excluded_covered = 0
    alternative_detected = alternative_covered = 0
    for draw in range(_DRAWS):
        study, runs = _draw(rng, alternative=False)
        baseline = analyze(study, runs, bootstrap_iterations=_BOOTSTRAPS, bootstrap_seed=draw)
        excluded = recompute_scenario(study, runs, baseline, exclude_errored=True)
        assert not excluded.unavailable_claims
        null_rejected += any(c.rejects_null for c in baseline.claims)
        null_covered += baseline.claims[0].delta_ci_low <= 0 <= baseline.claims[0].delta_ci_high
        excluded_rejected += any(c.rejects_null for c in excluded.result.claims)
        claim = excluded.result.claims[0]
        excluded_covered += claim.delta_ci_low <= 0 <= claim.delta_ci_high

        study, runs = _draw(rng, alternative=True)
        alternative = analyze(study, runs, bootstrap_iterations=_BOOTSTRAPS, bootstrap_seed=draw)
        claim = alternative.claims[0]
        alternative_detected += claim.rejects_null and claim.delta_point_estimate > 0
        alternative_covered += claim.delta_ci_low <= 0.30 <= claim.delta_ci_high
    return CalibrationCounts(
        null_rejected,
        null_covered,
        excluded_rejected,
        excluded_covered,
        alternative_detected,
        alternative_covered,
    )


def test_null_family_rejection_within_predeclared_binomial_bound(calibration_counts) -> None:
    assert calibration_counts.null_family_rejections <= _MAX_NULL_REJECTIONS, calibration_counts
    assert calibration_counts.excluded_null_family_rejections <= _MAX_NULL_REJECTIONS, (
        calibration_counts
    )


def test_interval_coverage_within_predeclared_binomial_bound(calibration_counts) -> None:
    assert calibration_counts.null_covered >= _MIN_COVERED, calibration_counts
    assert calibration_counts.excluded_null_covered >= _MIN_COVERED, calibration_counts
    assert calibration_counts.alternative_covered >= _MIN_COVERED, calibration_counts


def test_large_effect_detection_within_predeclared_binomial_bound(calibration_counts) -> None:
    assert calibration_counts.alternative_detected >= _MIN_DETECTED, calibration_counts
