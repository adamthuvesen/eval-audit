"""Acceptance tests for the StudySpec schema and YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_study_spec__loading_the_gaia_hal_generalist_study_spec_succeeds(repo_root: Path) -> None:
    """WHEN StudySpec.from_yaml("studies/gaia-hal-generalist.yaml") is called and the file
    declares the GAIA Claude-3.7 vs o4-mini-high claim,
    THEN a StudySpec instance is returned with claims[0].treatment == 'gaia_hg_claude37'
    and claims[0].control == 'gaia_hg_o4mini_high'.
    """
    from eval_audit.schema import StudySpec

    spec = StudySpec.from_yaml(repo_root / "studies" / "gaia-hal-generalist.yaml")

    assert spec.schema_version == 1
    assert spec.id == "gaia-hal-generalist"
    assert spec.benchmark == "gaia"
    assert spec.harness == "hal_generalist_agent"
    assert spec.analysis_mode == "declared_reanalysis"
    assert spec.inference.correction_method == "holm_bonferroni"
    assert spec.inference.alpha == 0.05
    # Long-form agent IDs verbatim from the locked GAIA column mapping
    # (scouting/gaia-hal-generalist-decision.md). RunRecord.agent_id is a pass-through.
    assert spec.claims[0].treatment == "HAL Generalist Agent (claude-3-7-sonnet-20250219)"
    assert spec.claims[0].control == "HAL Generalist Agent (o4-mini-2025-04-16 high)"
    assert spec.claims[0].outcome == "success_rate"


def _minimal_valid_study_yaml(*, schema_version_line: str | None = None) -> str:
    """Build a minimal valid study YAML, optionally with an explicit schema_version."""
    header = f"{schema_version_line}\n" if schema_version_line is not None else ""
    return f"""\
{header}id: tiny
benchmark: bench
analysis_mode: declared_reanalysis
data_observation: summary_seen
harness: tiny
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
cost:
  metrics: ["reconstructed_per_task_cost_usd"]
  primary_view: pareto_frontier
claims:
  - id: a_vs_b
    text: a beats b
    treatment: a
    control: b
    outcome: success_rate
"""


def test_study_spec__defaults_schema_version_to_one(tmp_path: Path) -> None:
    """WHEN a YAML file omits schema_version entirely,
    THEN the resulting StudySpec has schema_version == 1 and validates.
    """
    from eval_audit.schema import StudySpec

    path = tmp_path / "no-version.yaml"
    path.write_text(_minimal_valid_study_yaml())

    spec = StudySpec.from_yaml(path)
    assert spec.schema_version == 1


def test_study_spec__accepts_explicit_schema_version_one(tmp_path: Path) -> None:
    """WHEN a YAML file declares schema_version: 1,
    THEN the resulting StudySpec has schema_version == 1 and validates.
    """
    from eval_audit.schema import StudySpec

    path = tmp_path / "explicit-v1.yaml"
    path.write_text(_minimal_valid_study_yaml(schema_version_line="schema_version: 1"))

    spec = StudySpec.from_yaml(path)
    assert spec.schema_version == 1


def test_study_spec__rejects_unknown_schema_version(tmp_path: Path) -> None:
    """WHEN a YAML file declares schema_version: 2,
    THEN validation fails with a message naming both the field and the value.
    """
    from pydantic import ValidationError

    from eval_audit.schema import StudySpec

    path = tmp_path / "v2.yaml"
    path.write_text(_minimal_valid_study_yaml(schema_version_line="schema_version: 2"))

    with pytest.raises(ValidationError) as exc_info:
        StudySpec.from_yaml(path)

    msg = str(exc_info.value)
    assert "schema_version" in msg
    assert "2" in msg
    assert "1" in msg  # message names the supported value too


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
  unit: task
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


def test_study_spec__rejects_non_task_primary_outcome_unit(tmp_path: Path) -> None:
    """WHEN primary_outcome.unit is not task,
    THEN validation fails because v0 analysis is task-level only.
    """
    from pydantic import ValidationError

    from eval_audit.schema import StudySpec

    path = tmp_path / "bad-unit.yaml"
    path.write_text(_minimal_valid_study_yaml().replace("unit: task", "unit: request"))

    with pytest.raises(ValidationError) as exc_info:
        StudySpec.from_yaml(path)

    msg = str(exc_info.value)
    assert "unit" in msg
    assert "task" in msg


def test_study_spec__rejects_target_mde_above_one(tmp_path: Path) -> None:
    """WHEN target_mde is above the success-rate delta bound,
    THEN validation fails before the report can render nonsensical MDE context.
    """
    from pydantic import ValidationError

    from eval_audit.schema import StudySpec

    path = tmp_path / "bad-mde.yaml"
    path.write_text(
        _minimal_valid_study_yaml().replace(
            "comparison_family: declared_claims",
            "comparison_family: declared_claims\n  target_mde: 1.50",
        )
    )

    with pytest.raises(ValidationError) as exc_info:
        StudySpec.from_yaml(path)

    msg = str(exc_info.value)
    assert "target_mde" in msg
    assert "<= 1" in msg


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


def test_study_spec__unsupported_cost_view_fails_validation(tmp_path: Path) -> None:
    """WHEN a study declares summary_table as cost.primary_view,
    THEN validation fails because v0 only implements the Pareto cost view.
    """
    from pydantic import ValidationError

    from eval_audit.schema import StudySpec

    bad_yaml = """\
id: bad-cost-view
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
cost:
  metrics: ["cost_per_success_usd"]
  primary_view: summary_table
claims:
  - id: c
    text: a beats b
    treatment: a
    control: b
    outcome: success_rate
"""
    bad_path = tmp_path / "bad-cost-view.yaml"
    bad_path.write_text(bad_yaml)

    with pytest.raises(ValidationError) as exc_info:
        StudySpec.from_yaml(bad_path)

    msg = str(exc_info.value)
    assert "primary_view" in msg
    assert "pareto_frontier" in msg


def test_study_spec__unsupported_cost_metric_fails_validation(tmp_path: Path) -> None:
    """WHEN a study declares a metric the v0 report ignores,
    THEN validation fails instead of accepting a misleading declaration.
    """
    from pydantic import ValidationError

    from eval_audit.schema import StudySpec

    bad_yaml = """\
id: bad-cost-metric
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
cost:
  metrics: ["latency_s"]
  primary_view: pareto_frontier
claims:
  - id: c
    text: a beats b
    treatment: a
    control: b
    outcome: success_rate
"""
    bad_path = tmp_path / "bad-cost-metric.yaml"
    bad_path.write_text(bad_yaml)

    with pytest.raises(ValidationError) as exc_info:
        StudySpec.from_yaml(bad_path)

    msg = str(exc_info.value)
    assert "latency_s" in msg
    assert "cost.metrics" in msg
