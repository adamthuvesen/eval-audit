"""Shared readiness and analysis input boundary tests."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from eval_audit.checks import check_evidence
from eval_audit.errors import AnalysisInputError
from eval_audit.evidence import prepare_evidence
from eval_audit.schema import AgentRef, StudySpec
from eval_audit.stats import analyze


@pytest.fixture
def evidence(repo_root: Path) -> tuple[StudySpec, pl.DataFrame]:
    study = StudySpec.from_yaml(repo_root / "examples/byo-minimal/study.yaml")
    runs = pl.read_parquet(repo_root / "examples/byo-minimal/runs.parquet")
    return study, runs


@pytest.mark.parametrize("defect", ["harness", "tasks", "replication", "duplicate", "missing"])
def test_unclaimed_pareto_agent_uses_same_boundary(
    evidence: tuple[StudySpec, pl.DataFrame], repo_root: Path, defect: str
) -> None:
    study, runs = evidence
    study.agents.append(AgentRef(id="extra"))
    extra = runs.filter(pl.col("agent_id") == "alice").with_columns(
        pl.lit("extra").alias("agent_id")
    )
    if defect == "harness":
        extra = extra.with_columns(pl.lit("different-harness").alias("harness"))
    elif defect == "tasks":
        extra = extra.slice(1)
    elif defect == "replication":
        extra = pl.concat([extra, extra.with_columns(pl.lit("extra-run").alias("run_id"))])
    elif defect == "duplicate":
        extra = pl.concat([extra, extra.head(1)])
    elif defect == "missing":
        extra = extra.clear()
    runs = pl.concat([runs, extra])
    readiness = check_evidence(study, runs, repo_root=repo_root)
    assert readiness.status == "not_ready"
    with pytest.raises(AnalysisInputError) as error:
        analyze(study, runs, bootstrap_iterations=10)
    failed_readiness_ids = {
        check.id
        for check in readiness.checks
        if check.severity == "error" and check.status == "fail"
    }
    assert {
        check.id
        for check in error.value.diagnostics
        if check.severity == "error" and check.status == "fail"
    } == failed_readiness_ids


def test_reported_cost_total_must_be_unique_for_each_agent_run(
    evidence: tuple[StudySpec, pl.DataFrame], repo_root: Path
) -> None:
    study, runs = evidence
    runs = (
        runs.with_columns(
            pl.lit("as_reported_only").alias("cost_provenance"),
            pl.lit(None, dtype=pl.Float64).alias("reconstructed_per_task_cost_usd"),
        )
        .with_row_index("row_index")
        .with_columns(
            pl.when(pl.col("row_index") == 0)
            .then(pl.col("reported_run_total_cost_usd") + 1)
            .otherwise(pl.col("reported_run_total_cost_usd"))
            .alias("reported_run_total_cost_usd")
        )
        .drop("row_index")
    )
    readiness = check_evidence(study, runs, repo_root=repo_root)
    assert readiness.status == "not_ready"
    with pytest.raises(AnalysisInputError, match="one non-null total per agent/run"):
        analyze(study, runs, bootstrap_iterations=10)


def test_prepared_evidence_owns_study_copy_and_records_excluded_scope(
    evidence: tuple[StudySpec, pl.DataFrame],
) -> None:
    study, runs = evidence
    extra = runs.head(1).with_columns(pl.lit("undeclared").alias("agent_id"))
    prepared = prepare_evidence(study, pl.concat([runs, extra]))
    assert prepared.excluded_agent_ids == ("undeclared",)
    assert prepared.excluded_row_count == 1
    assert prepared.runs.height == runs.height
    assert set(prepared.rows_by_agent) == {"alice", "bob"}
    assert prepared.diagnostics[-1].id == "declared_agent_scope"
    study.agents.clear()
    assert len(prepared.study.agents) == 2


def test_mutated_study_is_revalidated_at_public_analysis_boundary(
    evidence: tuple[StudySpec, pl.DataFrame],
) -> None:
    study, runs = evidence
    study.agents.append(study.agents[0])
    with pytest.raises(AnalysisInputError, match="duplicate agent"):
        analyze(study, runs, bootstrap_iterations=10)


def test_public_analysis_rejects_coercible_success_with_structured_field_error(
    evidence: tuple[StudySpec, pl.DataFrame], repo_root: Path
) -> None:
    study, runs = evidence
    runs = runs.with_columns(pl.col("success").cast(pl.String))
    readiness = check_evidence(study, runs, repo_root=repo_root)
    assert readiness.status == "not_ready"
    with pytest.raises(AnalysisInputError, match="success") as error:
        analyze(study, runs, bootstrap_iterations=10)
    diagnostic = error.value.diagnostics[0]
    assert diagnostic.id == "runs_load"
    assert diagnostic.details == {"row_index": 0, "field_path": "success"}


def test_invalid_mutated_study_produces_json_readiness_diagnostic(
    evidence: tuple[StudySpec, pl.DataFrame], repo_root: Path
) -> None:
    study, runs = evidence
    study.inference.target_mde = float("nan")
    readiness = check_evidence(study, runs, repo_root=repo_root)
    assert readiness.status == "not_ready"
    assert '"study_loads"' in readiness.to_json()


def test_invalid_nested_study_copy_is_rejected_without_attribute_error(
    evidence: tuple[StudySpec, pl.DataFrame], repo_root: Path
) -> None:
    study, runs = evidence
    malformed = study.model_copy(update={"primary_outcome": "invalid"})
    with pytest.warns(UserWarning, match="PydanticSerializationUnexpectedValue"):
        readiness = check_evidence(malformed, runs, repo_root=repo_root)
    assert readiness.status == "not_ready"
    with (
        pytest.warns(UserWarning, match="PydanticSerializationUnexpectedValue"),
        pytest.raises(AnalysisInputError, match="primary_outcome"),
    ):
        analyze(malformed, runs, bootstrap_iterations=10)
