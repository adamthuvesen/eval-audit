"""Acceptance tests for the StudySpec schema and YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_study_spec__loading_the_exhibit_a_study_spec_succeeds(repo_root: Path) -> None:
    """WHEN StudySpec.from_yaml("studies/exhibit-a.yaml") is called and the file
    declares the GAIA Claude-3.7 vs o4-mini-high claim,
    THEN a StudySpec instance is returned with claims[0].treatment == 'gaia_hg_claude37'
    and claims[0].control == 'gaia_hg_o4mini_high'.
    """
    from eval_audit.schema import StudySpec

    spec = StudySpec.from_yaml(repo_root / "studies" / "exhibit-a.yaml")

    assert spec.id == "exhibit-a"
    assert spec.benchmark == "gaia"
    assert spec.harness == "hal_generalist_agent"
    assert spec.analysis_mode == "declared_reanalysis"
    assert spec.inference.correction_method == "holm_bonferroni"
    assert spec.inference.alpha == 0.05
    # Long-form agent IDs verbatim from the locked GAIA column mapping
    # (scouting/exhibit-a-decision.md). RunRecord.agent_id is a pass-through.
    assert spec.claims[0].treatment == "HAL Generalist Agent (claude-3-7-sonnet-20250219)"
    assert spec.claims[0].control == "HAL Generalist Agent (o4-mini-2025-04-16 high)"
    assert spec.claims[0].outcome == "success_rate"


def test_study_spec__multiple_validation_errors_are_surfaced_together(tmp_path: Path) -> None:
    """WHEN a YAML file is loaded that is missing both analysis_mode and harness,
    THEN the raised error mentions both missing fields, not only the first.
    """
    from pydantic import ValidationError

    from eval_audit.schema import StudySpec

    bad_yaml = """\
id: broken-study
benchmark: gaia
data_observation: summary_seen
primary_outcome:
  name: success_rate
  unit: task
  direction: higher_is_better
agents:
  - id: a
  - id: b
design:
  task_sampling: fixed_public_validation_set
  run_strategy: observed_public_runs
  observed_runs_per_agent: 1
  rerun_policy: recommend_if_decision_sensitive
inference:
  alpha: 0.05
  correction_method: holm_bonferroni
  comparison_family: declared_claims
  target_mde: 0.03
cost:
  metrics: ["x"]
  primary_view: pareto_frontier
claims:
  - id: c
    text: t
    treatment: a
    control: b
    outcome: success_rate
"""
    bad_path = tmp_path / "broken.yaml"
    bad_path.write_text(bad_yaml)

    with pytest.raises(ValidationError) as exc_info:
        StudySpec.from_yaml(bad_path)

    msg = str(exc_info.value)
    assert "analysis_mode" in msg
    assert "harness" in msg


def test_study_spec__invalid_invariants_fail_validation_together(tmp_path: Path) -> None:
    """WHEN a study violates multiple v0 StudySpec invariants,
    THEN validation fails with a message naming each invalid field.
    """
    from pydantic import ValidationError

    from eval_audit.schema import StudySpec

    bad_yaml = """\
id: broken-study
benchmark: gaia
analysis_mode: declared_reanalysis
data_observation: summary_seen
harness: hal_generalist_agent
primary_outcome:
  name: latency_s
  unit: second
  direction: lower_is_better
agents: []
design:
  task_sampling: fixed_public_validation_set
  run_strategy: observed_public_runs
  observed_runs_per_agent: 0
  rerun_policy: recommend_if_decision_sensitive
inference:
  alpha: 1.5
  correction_method: holm_bonferroni
  comparison_family: declared_claims
  target_mde: -0.01
cost:
  metrics: []
  primary_view: pareto_frontier
claims: []
"""
    bad_path = tmp_path / "broken-invariants.yaml"
    bad_path.write_text(bad_yaml)

    with pytest.raises(ValidationError) as exc_info:
        StudySpec.from_yaml(bad_path)

    msg = str(exc_info.value)
    for expected in (
        "agents",
        "claims",
        "observed_runs_per_agent",
        "alpha",
        "target_mde",
        "success_rate",
        "higher_is_better",
    ):
        assert expected in msg


def test_study_spec__claim_family_invariants_fail_validation(tmp_path: Path) -> None:
    """WHEN claims reference unknown agents, duplicate ids, compare an agent to itself,
    or declare a non-success-rate outcome, THEN validation fails before analysis.
    """
    from pydantic import ValidationError

    from eval_audit.schema import StudySpec

    bad_yaml = """\
id: broken-claims
benchmark: gaia
analysis_mode: declared_reanalysis
data_observation: summary_seen
harness: hal_generalist_agent
primary_outcome:
  name: success_rate
  unit: task
  direction: higher_is_better
agents:
  - id: a
design:
  task_sampling: fixed_public_validation_set
  run_strategy: observed_public_runs
  observed_runs_per_agent: 1
  rerun_policy: recommend_if_decision_sensitive
inference:
  alpha: 0.05
  correction_method: holm_bonferroni
  comparison_family: declared_claims
  target_mde: 0.03
cost:
  metrics: ["success_rate"]
  primary_view: pareto_frontier
claims:
  - id: duplicate
    text: a beats b
    treatment: a
    control: b
    outcome: partial_credit
  - id: duplicate
    text: a beats itself
    treatment: a
    control: a
    outcome: success_rate
"""
    bad_path = tmp_path / "broken-claims.yaml"
    bad_path.write_text(bad_yaml)

    with pytest.raises(ValidationError) as exc_info:
        StudySpec.from_yaml(bad_path)

    msg = str(exc_info.value)
    for expected in ("duplicate", "unknown", "b", "treatment", "control", "partial_credit"):
        assert expected in msg
