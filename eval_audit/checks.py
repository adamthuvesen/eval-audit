"""Audit-readiness checks for declared eval-audit evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import ValidationError

from eval_audit.ingest import IngestContractError
from eval_audit.ingest.generic import load_run_records
from eval_audit.schema import StudySpec
from eval_audit.schema.enums import CostProvenance
from eval_audit.scouting_paths import resolve_decision_doc

ReadinessStatus = Literal["ready", "ready_with_warnings", "not_ready"]
CheckSeverity = Literal["error", "warning", "info"]
CheckStatus = Literal["pass", "fail"]
JsonScalar = str | int | float | bool | None
Json = JsonScalar | list["Json"] | dict[str, "Json"]


@dataclass(frozen=True)
class ReadinessCheck:
    id: str
    severity: CheckSeverity
    status: CheckStatus
    message: str
    details: dict[str, Json]
    fix_suggestion: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "severity": self.severity,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "fix_suggestion": self.fix_suggestion,
        }


@dataclass(frozen=True)
class ReadinessResult:
    study_id: str | None
    status: ReadinessStatus
    checks: list[ReadinessCheck]

    def to_dict(self) -> dict[str, object]:
        return {
            "study_id": self.study_id,
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    def to_json_bytes(self) -> bytes:
        return self.to_json().encode()


def render_readiness_text(result: ReadinessResult) -> str:
    errors = _count_failed(result, "error")
    warnings = _count_failed(result, "warning")
    lines = [
        f"status: {result.status}",
        f"study: {result.study_id or 'n/a'}",
        "",
        f"errors: {errors}",
        f"warnings: {warnings}",
    ]
    failed = [check for check in result.checks if check.status == "fail"]
    if failed:
        lines.append("")
        for check in failed:
            lines.append(f"[{check.severity}] {check.id}: {check.message}")
            if check.fix_suggestion is not None:
                lines.append(f"  fix: {check.fix_suggestion}")
    return "\n".join(lines) + "\n"


def check_paths(
    study_yaml: Path,
    runs_parquet: Path,
    *,
    repo_root: Path,
) -> ReadinessResult:
    checks: list[ReadinessCheck] = []
    study: StudySpec | None = None
    runs: pl.DataFrame | None = None

    try:
        study = StudySpec.from_yaml(study_yaml)
    except (FileNotFoundError, ValidationError, ValueError) as exc:
        checks.append(
            _check(
                "study_loads",
                "error",
                "fail",
                str(exc),
                {"path": str(study_yaml)},
            )
        )
    else:
        checks.append(
            _check(
                "study_loads",
                "error",
                "pass",
                "study YAML loaded",
                {"path": str(study_yaml)},
            )
        )

    try:
        runs = load_run_records(runs_parquet)
    except (FileNotFoundError, IngestContractError) as exc:
        checks.append(
            _check(
                "runs_load",
                "error",
                "fail",
                str(exc),
                {"path": str(runs_parquet)},
            )
        )
    else:
        checks.append(
            _check(
                "runs_load",
                "error",
                "pass",
                "runs parquet loaded",
                {"path": str(runs_parquet), "rows": runs.height},
            )
        )

    if study is None or runs is None:
        return _result(study.id if study is not None else None, checks)
    return check_loaded_evidence(
        study_yaml,
        runs_parquet,
        study,
        runs,
        repo_root=repo_root,
        initial_checks=checks,
    )


def check_loaded_evidence(
    study_yaml: Path,
    runs_parquet: Path,
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    repo_root: Path,
    initial_checks: list[ReadinessCheck] | None = None,
) -> ReadinessResult:
    checks = list(initial_checks or [])
    if not initial_checks:
        checks.extend(
            [
                _check(
                    "study_loads",
                    "error",
                    "pass",
                    "study YAML loaded",
                    {"path": str(study_yaml)},
                ),
                _check(
                    "runs_load",
                    "error",
                    "pass",
                    "runs parquet loaded",
                    {"path": str(runs_parquet), "rows": runs.height},
                ),
            ]
        )
    return check_evidence(study, runs, repo_root=repo_root, initial_checks=checks)


def check_evidence(
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    repo_root: Path,
    initial_checks: list[ReadinessCheck] | None = None,
) -> ReadinessResult:
    checks = list(initial_checks or [])
    if not initial_checks:
        checks.extend(
            [
                _check("study_loads", "error", "pass", "study YAML loaded", {}),
                _check(
                    "runs_load",
                    "error",
                    "pass",
                    "runs parquet loaded",
                    {"rows": runs.height},
                ),
            ]
        )

    checks.append(_claim_agents_present(study, runs))
    checks.append(_claimed_rows_match_study_harness(study, runs))
    checks.append(_paired_tasks_complete(study, runs))
    checks.append(_outcome_supported(study))
    checks.append(_cost_provenance_explicit(study, runs))
    checks.append(_target_mde_declared(study))
    checks.append(_residual_risks_source(study, repo_root))
    return _result(study.id, checks)


def _claim_agents_present(study: StudySpec, runs: pl.DataFrame) -> ReadinessCheck:
    missing: list[str] = []
    for claim in study.claims:
        for role, agent_id in (
            ("treatment", claim.treatment),
            ("control", claim.control),
        ):
            if runs.filter(pl.col("agent_id") == agent_id).height == 0:
                missing.append(f"{claim.id}:{role}:{agent_id}")
    if missing:
        return _check(
            "claim_agents_present",
            "error",
            "fail",
            "one or more claimed agents have no rows in the run data",
            {"missing": sorted(missing)},
        )
    return _check(
        "claim_agents_present",
        "error",
        "pass",
        "all claimed agents have rows",
        {"claims": [claim.id for claim in study.claims]},
    )


def _claimed_rows_match_study_harness(study: StudySpec, runs: pl.DataFrame) -> ReadinessCheck:
    mismatches: list[str] = []
    for claim in study.claims:
        for role, agent_id in (
            ("treatment", claim.treatment),
            ("control", claim.control),
        ):
            rows = runs.filter(pl.col("agent_id") == agent_id)
            if rows.is_empty():
                continue
            harnesses = sorted(str(value) for value in rows["harness"].unique().to_list())
            bad = [value for value in harnesses if value != study.harness]
            if bad:
                mismatches.append(f"{claim.id}:{role}:{agent_id}:{bad}")
    if mismatches:
        return _check(
            "claimed_rows_match_study_harness",
            "error",
            "fail",
            "claimed rows must all match study.harness",
            {"study_harness": study.harness, "mismatches": sorted(mismatches)},
        )
    return _check(
        "claimed_rows_match_study_harness",
        "error",
        "pass",
        "claimed rows match study.harness",
        {"study_harness": study.harness},
    )


def _paired_tasks_complete(study: StudySpec, runs: pl.DataFrame) -> ReadinessCheck:
    failures: list[str] = []
    treatment_counts: list[int] = []
    control_counts: list[int] = []
    paired_counts: list[int] = []
    missing_treatment_counts: list[int] = []
    missing_control_counts: list[int] = []
    duplicate_observation_keys: list[str] = []
    invalid_run_count_keys: list[str] = []

    for claim in study.claims:
        claim_duplicate_keys: list[str] = []
        claim_invalid_run_count_keys: list[str] = []
        treatment_tasks = _task_set(runs, claim.treatment)
        control_tasks = _task_set(runs, claim.control)
        paired = treatment_tasks & control_tasks
        missing_treatment = control_tasks - treatment_tasks
        missing_control = treatment_tasks - control_tasks

        treatment_counts.append(len(treatment_tasks))
        control_counts.append(len(control_tasks))
        paired_counts.append(len(paired))
        missing_treatment_counts.append(len(missing_treatment))
        missing_control_counts.append(len(missing_control))

        for role, agent_id in (
            ("treatment", claim.treatment),
            ("control", claim.control),
        ):
            rows = runs.filter(pl.col("agent_id") == agent_id)
            claim_duplicate_keys.extend(
                _duplicate_observation_keys(claim.id, role, agent_id, rows)
            )
            claim_invalid_run_count_keys.extend(
                _invalid_task_run_count_keys(
                    claim.id,
                    role,
                    agent_id,
                    rows,
                    expected_runs=study.design.observed_runs_per_agent,
                )
            )

        duplicate_observation_keys.extend(claim_duplicate_keys)
        invalid_run_count_keys.extend(claim_invalid_run_count_keys)
        if (
            missing_treatment
            or missing_control
            or not paired
            or claim_duplicate_keys
            or claim_invalid_run_count_keys
        ):
            failures.append(claim.id)

    details = {
        "claims": [claim.id for claim in study.claims],
        "treatment_task_counts": treatment_counts,
        "control_task_counts": control_counts,
        "paired_task_counts": paired_counts,
        "missing_treatment_task_counts": missing_treatment_counts,
        "missing_control_task_counts": missing_control_counts,
    }
    if duplicate_observation_keys:
        details["duplicate_observation_keys"] = sorted(set(duplicate_observation_keys))
    if invalid_run_count_keys:
        details["invalid_task_run_counts"] = sorted(set(invalid_run_count_keys))
    if failures:
        details["failed_claims"] = sorted(set(failures))
        return _check(
            "paired_tasks_complete",
            "error",
            "fail",
            "declared claims must have complete paired task observations",
            details,
        )
    return _check(
        "paired_tasks_complete",
        "error",
        "pass",
        "declared claims have complete paired task observations",
        details,
    )


def _duplicate_observation_keys(
    claim_id: str,
    role: str,
    agent_id: str,
    rows: pl.DataFrame,
) -> list[str]:
    seen: set[tuple[str, str]] = set()
    duplicates: set[str] = set()
    for row in rows.select(["task_id", "run_id"]).iter_rows(named=True):
        task_id = str(row["task_id"])
        run_id = str(row["run_id"])
        key = (task_id, run_id)
        if key in seen:
            duplicates.add(f"{claim_id}:{role}:{agent_id}:{task_id}:{run_id}")
            continue
        seen.add(key)
    return sorted(duplicates)


def _invalid_task_run_count_keys(
    claim_id: str,
    role: str,
    agent_id: str,
    rows: pl.DataFrame,
    *,
    expected_runs: int,
) -> list[str]:
    runs_by_task: dict[str, set[str]] = {}
    for row in rows.select(["task_id", "run_id"]).iter_rows(named=True):
        task_id = str(row["task_id"])
        run_id = str(row["run_id"])
        runs_by_task.setdefault(task_id, set()).add(run_id)

    invalid: list[str] = []
    for task_id, run_ids in sorted(runs_by_task.items()):
        observed_runs = len(run_ids)
        if observed_runs != expected_runs:
            invalid.append(
                f"{claim_id}:{role}:{agent_id}:{task_id}:"
                f"expected={expected_runs}:observed={observed_runs}"
            )
    return invalid


def _outcome_supported(study: StudySpec) -> ReadinessCheck:
    failures: list[str] = []
    if study.primary_outcome.name != "success_rate":
        failures.append(f"primary_outcome.name={study.primary_outcome.name}")
    if study.primary_outcome.direction != "higher_is_better":
        failures.append(f"primary_outcome.direction={study.primary_outcome.direction}")
    for claim in study.claims:
        if claim.outcome != "success_rate":
            failures.append(f"claim.{claim.id}.outcome={claim.outcome}")
    if failures:
        return _check(
            "outcome_supported",
            "error",
            "fail",
            "v0 supports only higher-is-better success_rate outcomes",
            {"unsupported": sorted(failures)},
        )
    return _check(
        "outcome_supported",
        "error",
        "pass",
        "v0 outcome contract is supported",
        {"outcome": "success_rate", "direction": "higher_is_better"},
    )


def _cost_provenance_explicit(study: StudySpec, runs: pl.DataFrame) -> ReadinessCheck:
    claimed_agents = sorted(
        {agent_id for claim in study.claims for agent_id in (claim.treatment, claim.control)}
    )
    claimed_rows = runs.filter(pl.col("agent_id").is_in(claimed_agents))
    if claimed_rows.is_empty():
        return _check(
            "cost_provenance_explicit",
            "error",
            "fail",
            "no claimed rows are available for cost-provenance checks",
            {"claimed_agents": claimed_agents},
        )

    provenance_values = sorted(
        str(value) for value in claimed_rows["cost_provenance"].unique().to_list()
    )
    errors: list[str] = []
    warnings: list[str] = []

    for agent_id in claimed_agents:
        rows = claimed_rows.filter(pl.col("agent_id") == agent_id)
        if rows.is_empty():
            continue
        agent_values = sorted(str(value) for value in rows["cost_provenance"].unique().to_list())
        if CostProvenance.COST_NOT_AVAILABLE.value in agent_values and len(agent_values) > 1:
            errors.append(f"{agent_id}: mixed cost_not_available with {agent_values}")
        if agent_values == [CostProvenance.COST_NOT_AVAILABLE.value]:
            continue

        graded = rows.filter(pl.col("outcome_status") == "graded")
        if not graded.is_empty():
            null_reconstructed = graded["reconstructed_per_task_cost_usd"].null_count()
            if 0 < null_reconstructed < graded.height:
                errors.append(
                    f"{agent_id}: incomplete reconstructed_per_task_cost_usd "
                    f"({null_reconstructed}/{graded.height} graded rows null)"
                )
            elif (
                null_reconstructed == graded.height
                and rows["reported_run_total_cost_usd"].null_count() > 0
            ):
                errors.append(
                    f"{agent_id}: no reconstructed cost and missing reported_run_total_cost_usd"
                )

    if CostProvenance.AS_REPORTED_ONLY.value in provenance_values:
        warnings.append("cost provenance is as_reported_only")
    if CostProvenance.COST_NOT_AVAILABLE.value in provenance_values:
        warnings.append(
            "cost provenance is cost_not_available; cost-derived views will be suppressed"
        )
    if CostProvenance.PARTIAL.value in provenance_values:
        warnings.append("cost provenance is partial")

    details = {"cost_provenance": provenance_values}
    if errors:
        details["errors"] = sorted(errors)
        return _check(
            "cost_provenance_explicit",
            "error",
            "fail",
            "cost provenance is incomplete or internally inconsistent",
            details,
        )
    if warnings:
        details["warnings"] = sorted(warnings)
        return _check(
            "cost_provenance_explicit",
            "warning",
            "fail",
            "; ".join(sorted(warnings)),
            details,
        )
    return _check(
        "cost_provenance_explicit",
        "info",
        "pass",
        "cost provenance is reconciled",
        details,
    )


def _target_mde_declared(study: StudySpec) -> ReadinessCheck:
    if study.inference.target_mde is None:
        return _check(
            "target_mde_declared",
            "warning",
            "fail",
            "inference.target_mde is not declared",
            {},
        )
    return _check(
        "target_mde_declared",
        "warning",
        "pass",
        "inference.target_mde is declared",
        {"target_mde": study.inference.target_mde},
    )


def _residual_risks_source(study: StudySpec, repo_root: Path) -> ReadinessCheck:
    path, label = resolve_decision_doc(repo_root, study.benchmark, study.id)
    if not path.exists():
        return _check(
            "residual_risks_source",
            "warning",
            "fail",
            "no residual-risk/scouting decision document found",
            {"path": label},
        )
    return _check(
        "residual_risks_source",
        "info",
        "pass",
        "residual-risk/scouting decision document found",
        {"path": label},
    )


def _task_set(runs: pl.DataFrame, agent_id: str) -> set[str]:
    return set(
        str(value)
        for value in runs.filter(pl.col("agent_id") == agent_id)["task_id"].unique().to_list()
    )


def _check(
    check_id: str,
    severity: CheckSeverity,
    status: CheckStatus,
    message: str,
    details: dict[str, Json],
) -> ReadinessCheck:
    fix_suggestion = None if status == "pass" else _fix_suggestion(check_id, details)
    return ReadinessCheck(
        id=check_id,
        severity=severity,
        status=status,
        message=message,
        details=details,
        fix_suggestion=fix_suggestion,
    )


def _fix_suggestion(check_id: str, details: dict[str, Json]) -> str:
    if check_id == "study_loads":
        return (
            "Fix the study YAML path or schema errors so StudySpec.from_yaml() "
            "can load the declared audit."
        )
    if check_id == "runs_load":
        return (
            "Provide a readable canonical RunRecord parquet with the required task-level columns."
        )
    if check_id == "claim_agents_present":
        return (
            "Add run rows for every treatment and control agent named by each "
            "claim, or update the study claims to reference agents present in the runs."
        )
    if check_id == "claimed_rows_match_study_harness":
        return (
            "Cross-harness comparisons are not audit-ready; prepare a single-harness "
            "paired comparison that matches study.harness, or split the evidence into "
            "separate declared studies per harness."
        )
    if check_id == "paired_tasks_complete":
        return (
            "Add the missing paired task rows, remove duplicate task/run rows, "
            "and make every claimed agent match design.observed_runs_per_agent "
            "for each task id."
        )
    if check_id == "outcome_supported":
        return (
            "Declare a v0-supported success_rate, higher_is_better outcome for "
            "the study and every claim, or add metric-specific engine support first."
        )
    if check_id == "cost_provenance_explicit":
        values = details.get("cost_provenance")
        if isinstance(values, list) and "cost_not_available" in values:
            return (
                "Keep cost_not_available only when neither reconstructed per-task "
                "cost nor reported totals are honestly available, with both cost "
                "fields null on every row."
            )
        if isinstance(values, list) and "as_reported_only" in values:
            return (
                "Record the reported run totals and provenance notes that justify "
                "as_reported_only cost handling, or provide reconciled per-task costs."
            )
        return (
            "Make cost provenance internally consistent: provide complete "
            "reconstructed per-task costs, complete reported totals, or an explicit "
            "cost_not_available declaration."
        )
    if check_id == "target_mde_declared":
        return (
            "Declare inference.target_mde in the study YAML so the report can "
            "judge whether the paired evidence resolves the practical effect size."
        )
    if check_id == "residual_risks_source":
        return (
            "Add or restore the scouting decision document that records residual "
            "risks and provenance notes for this fixture."
        )
    return "Repair the failed readiness condition before running analysis or rendering a report."


def _result(study_id: str | None, checks: list[ReadinessCheck]) -> ReadinessResult:
    if _count_failed_checks(checks, "error") > 0:
        status: ReadinessStatus = "not_ready"
    elif _count_failed_checks(checks, "warning") > 0:
        status = "ready_with_warnings"
    else:
        status = "ready"
    return ReadinessResult(study_id=study_id, status=status, checks=checks)


def _count_failed(result: ReadinessResult, severity: CheckSeverity) -> int:
    return _count_failed_checks(result.checks, severity)


def _count_failed_checks(checks: list[ReadinessCheck], severity: CheckSeverity) -> int:
    return sum(1 for check in checks if check.severity == severity and check.status == "fail")
