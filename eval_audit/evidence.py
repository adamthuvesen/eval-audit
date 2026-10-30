"""Shared validation and declared scope for canonical study evidence."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

import polars as pl
from pydantic import ValidationError

from eval_audit.errors import (
    AnalysisInputError,
    CostProvenanceError,
    CrossHarnessComparisonError,
    UnsupportedOutcomeError,
)
from eval_audit.ingest.base import IngestContractError, validate_run_records
from eval_audit.schema import Claim, PrimaryOutcome, StudySpec
from eval_audit.schema.enums import CostProvenance

JsonScalar = str | int | float | bool | None
Json = JsonScalar | list["Json"] | dict[str, "Json"]
CheckSeverity = Literal["error", "warning", "info"]
CheckStatus = Literal["pass", "fail"]


@dataclass(frozen=True)
class EvidenceCheck:
    id: str
    severity: CheckSeverity
    status: CheckStatus
    message: str
    details: dict[str, Json]


@dataclass(frozen=True)
class PreparedEvidence:
    """Owned study copy and scoped frames that passed evidence validation.

    The contained models and frames remain mutable. Consumers must not mutate them.
    """

    study: StudySpec
    runs: pl.DataFrame
    rows_by_agent: dict[str, pl.DataFrame]
    excluded_agent_ids: tuple[str, ...]
    excluded_row_count: int
    diagnostics: tuple[EvidenceCheck, ...]


def inspect_evidence(study: StudySpec, runs: pl.DataFrame) -> tuple[EvidenceCheck, ...]:
    """Return the same input checks used by prepare_evidence without raising."""
    return _inspect(study, runs).diagnostics


def prepare_evidence(study: StudySpec, runs: pl.DataFrame) -> PreparedEvidence:
    """Validate once and exclude unrelated agents with an explicit scope diagnostic."""
    evidence = _inspect(study, runs)
    failures = tuple(
        check
        for check in evidence.diagnostics
        if check.severity == "error" and check.status == "fail"
    )
    if failures:
        message = ". ".join(f"{check.id}: {check.message}" for check in failures)
        error_type: type[AnalysisInputError] = AnalysisInputError
        if any(check.id == "outcome_supported" for check in failures):
            error_type = UnsupportedOutcomeError
        elif any(check.details.get("cross_harness_claims") for check in failures):
            error_type = CrossHarnessComparisonError
        elif any(check.id == "cost_provenance_explicit" for check in failures):
            error_type = CostProvenanceError
        raise error_type(message, diagnostics=evidence.diagnostics)
    return evidence


def _inspect(study: StudySpec, runs: pl.DataFrame) -> PreparedEvidence:
    try:
        study = StudySpec.model_validate(study.model_dump())
    except ValidationError as exc:
        diagnostics = [_check("study_loads", "error", "fail", str(exc), {})]
        if (
            isinstance(study.primary_outcome, PrimaryOutcome)
            and isinstance(study.claims, list)
            and all(isinstance(claim, Claim) for claim in study.claims)
        ):
            outcome_check = _outcome_supported(study)
            if outcome_check.status == "fail":
                diagnostics.append(outcome_check)
        return PreparedEvidence(study, runs, {}, (), 0, tuple(diagnostics))
    outcome_check = _outcome_supported(study)
    try:
        validate_run_records(runs)
    except IngestContractError as exc:
        details: dict[str, Json] = {}
        if exc.row_index is not None:
            details["row_index"] = exc.row_index
        if exc.field_path is not None:
            details["field_path"] = exc.field_path
        diagnostic = _check("runs_load", "error", "fail", str(exc), details)
        return PreparedEvidence(study, runs, {}, (), 0, (diagnostic,))
    agent_ids = [agent.id for agent in study.agents]
    excluded = runs.filter(~pl.col("agent_id").is_in(agent_ids))
    scoped = runs.filter(pl.col("agent_id").is_in(agent_ids))
    excluded_agent_ids = tuple(sorted(excluded["agent_id"].unique().to_list()))
    diagnostics = [
        _claim_agents_present(study, scoped),
        _claimed_rows_match_study_harness(study, scoped),
        _paired_tasks_complete(study, scoped),
        outcome_check,
        _cost_provenance_explicit(study, scoped),
    ]
    if excluded.height:
        diagnostics.append(
            _check(
                "declared_agent_scope",
                "info",
                "pass",
                "excluded unrelated rows outside study.agents",
                {
                    "excluded_agent_ids": _json_array(excluded_agent_ids),
                    "excluded_row_count": excluded.height,
                },
            )
        )
    return PreparedEvidence(
        study,
        scoped,
        {agent_id: scoped.filter(pl.col("agent_id") == agent_id) for agent_id in agent_ids},
        excluded_agent_ids,
        excluded.height,
        tuple(diagnostics),
    )


def _json_array(values: Iterable[JsonScalar]) -> list[Json]:
    items: list[Json] = []
    items.extend(values)
    return items


def _check(
    check_id: str,
    severity: CheckSeverity,
    status: CheckStatus,
    message: str,
    details: dict[str, Json],
) -> EvidenceCheck:
    return EvidenceCheck(check_id, severity, status, message, details)


def _claim_agents_present(study: StudySpec, runs: pl.DataFrame) -> EvidenceCheck:
    missing: list[str] = []
    for claim in study.claims:
        for role, agent_id in (
            ("treatment", claim.treatment),
            ("control", claim.control),
        ):
            if runs.filter(pl.col("agent_id") == agent_id).height == 0:
                missing.append(f"{claim.id}:{role}:{agent_id}")
    for agent in study.agents:
        if runs.filter(pl.col("agent_id") == agent.id).is_empty() and not any(
            entry.endswith(f":{agent.id}") for entry in missing
        ):
            missing.append(f"declared:{agent.id}")
    if missing:
        return _check(
            "claim_agents_present",
            "error",
            "fail",
            f"one or more declared agents have no rows in the run data: {sorted(missing)}",
            {"missing": _json_array(sorted(missing))},
        )
    return _check(
        "claim_agents_present",
        "error",
        "pass",
        "all claimed agents have rows",
        {"claims": [claim.id for claim in study.claims]},
    )


def _claimed_rows_match_study_harness(study: StudySpec, runs: pl.DataFrame) -> EvidenceCheck:
    harness_by_agent = {
        agent.id: sorted(runs.filter(pl.col("agent_id") == agent.id)["harness"].unique().to_list())
        for agent in study.agents
    }
    mismatches = [
        f"{agent_id}:{harnesses}"
        for agent_id, harnesses in harness_by_agent.items()
        if harnesses and harnesses != [study.harness]
    ]
    cross_harness_claims = [
        claim.id
        for claim in study.claims
        if len(harness_by_agent[claim.treatment]) == 1
        and len(harness_by_agent[claim.control]) == 1
        and harness_by_agent[claim.treatment] != harness_by_agent[claim.control]
    ]
    if mismatches:
        return _check(
            "claimed_rows_match_study_harness",
            "error",
            "fail",
            f"declared rows must all match study.harness={study.harness!r}: {harness_by_agent}",
            {
                "study_harness": study.harness,
                "mismatches": _json_array(sorted(mismatches)),
                "cross_harness_claims": _json_array(cross_harness_claims),
            },
        )
    return _check(
        "claimed_rows_match_study_harness",
        "error",
        "pass",
        "claimed rows match study.harness",
        {"study_harness": study.harness},
    )


def _paired_tasks_complete(study: StudySpec, runs: pl.DataFrame) -> EvidenceCheck:
    tasks_by_agent: dict[str, set[str]] = {}
    duplicate_keys: list[str] = []
    invalid_run_counts: list[str] = []
    for agent in study.agents:
        rows = runs.filter(pl.col("agent_id") == agent.id)
        runs_by_task: dict[str, set[str]] = {}
        seen: set[tuple[str, str]] = set()
        for task_id, run_id in rows.select("task_id", "run_id").iter_rows():
            key = (task_id, run_id)
            if key in seen:
                duplicate_keys.append(f"{agent.id}:{task_id}:{run_id}")
            seen.add(key)
            runs_by_task.setdefault(task_id, set()).add(run_id)
        tasks_by_agent[agent.id] = set(runs_by_task)
        for task_id, run_ids in sorted(runs_by_task.items()):
            if len(run_ids) != study.design.observed_runs_per_agent:
                invalid_run_counts.append(
                    f"{agent.id}:{task_id}:expected={study.design.observed_runs_per_agent}"
                    f":observed={len(run_ids)}"
                )
        observed_runs = len(set(rows["run_id"].to_list()))
        if rows.height and observed_runs != study.design.observed_runs_per_agent:
            invalid_run_counts.append(
                f"{agent.id}:expected={study.design.observed_runs_per_agent}:observed={observed_runs}"
            )
    treatment_tasks = [tasks_by_agent[claim.treatment] for claim in study.claims]
    control_tasks = [tasks_by_agent[claim.control] for claim in study.claims]
    details: dict[str, Json] = {
        "claims": [claim.id for claim in study.claims],
        "treatment_task_counts": [len(tasks) for tasks in treatment_tasks],
        "control_task_counts": [len(tasks) for tasks in control_tasks],
        "paired_task_counts": [
            len(a & b) for a, b in zip(treatment_tasks, control_tasks, strict=True)
        ],
        "missing_treatment_task_counts": [
            len(b - a) for a, b in zip(treatment_tasks, control_tasks, strict=True)
        ],
        "missing_control_task_counts": [
            len(a - b) for a, b in zip(treatment_tasks, control_tasks, strict=True)
        ],
    }
    task_sets = list(tasks_by_agent.values())
    comparable = (
        bool(task_sets) and bool(task_sets[0]) and all(tasks == task_sets[0] for tasks in task_sets)
    )
    if not comparable:
        details["task_counts_by_agent"] = {
            agent: len(tasks) for agent, tasks in tasks_by_agent.items()
        }
    if duplicate_keys:
        details["duplicate_observation_keys"] = _json_array(sorted(set(duplicate_keys)))
    if invalid_run_counts:
        details["invalid_task_run_counts"] = _json_array(sorted(set(invalid_run_counts)))
    failed = not comparable or bool(duplicate_keys) or bool(invalid_run_counts)
    return _check(
        "paired_tasks_complete",
        "error",
        "fail" if failed else "pass",
        "all declared agents must have complete paired task observations and declared run exposure"
        if failed
        else "declared claims have complete paired task observations",
        details,
    )


def _outcome_supported(study: StudySpec) -> EvidenceCheck:
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
            {"unsupported": _json_array(sorted(failures))},
        )
    return _check(
        "outcome_supported",
        "error",
        "pass",
        "v0 outcome contract is supported",
        {"outcome": "success_rate", "direction": "higher_is_better"},
    )


def _cost_provenance_explicit(study: StudySpec, runs: pl.DataFrame) -> EvidenceCheck:
    claimed_agents = sorted(agent.id for agent in study.agents)
    claimed_rows = runs.filter(pl.col("agent_id").is_in(claimed_agents))
    if claimed_rows.is_empty():
        return _check(
            "cost_provenance_explicit",
            "error",
            "fail",
            "no claimed rows are available for cost-provenance checks",
            {"claimed_agents": _json_array(claimed_agents)},
        )

    provenance_values = sorted(
        str(value) for value in claimed_rows["cost_provenance"].unique().to_list()
    )
    errors = _cost_provenance_consistency_errors(claimed_agents, claimed_rows)
    warnings = _cost_provenance_warnings(provenance_values)
    return _cost_provenance_check(provenance_values, errors, warnings)


def _cost_provenance_consistency_errors(
    claimed_agents: list[str],
    claimed_rows: pl.DataFrame,
) -> list[str]:
    errors: list[str] = []
    for agent_id in claimed_agents:
        rows = claimed_rows.filter(pl.col("agent_id") == agent_id)
        if rows.is_empty():
            continue
        errors.extend(_agent_cost_provenance_errors(agent_id, rows))
    return errors


def _agent_cost_provenance_errors(agent_id: str, rows: pl.DataFrame) -> list[str]:
    agent_values = sorted(str(value) for value in rows["cost_provenance"].unique().to_list())
    if CostProvenance.COST_NOT_AVAILABLE.value in agent_values and len(agent_values) > 1:
        return [f"{agent_id}: mixed cost_not_available with {agent_values}"]
    if agent_values == [CostProvenance.COST_NOT_AVAILABLE.value]:
        return []

    graded = rows.filter(pl.col("outcome_status") == "graded")
    null_reconstructed = graded["reconstructed_per_task_cost_usd"].null_count()
    if 0 < null_reconstructed < graded.height:
        return [
            f"{agent_id}: incomplete reconstructed cost data for reconstructed_per_task_cost_usd "
            f"({null_reconstructed}/{graded.height} graded rows null)"
        ]
    if null_reconstructed == graded.height:
        errors: list[str] = []
        for run_id, run_rows in rows.group_by("run_id"):
            totals = run_rows["reported_run_total_cost_usd"]
            if totals.null_count() or totals.n_unique() != 1:
                errors.append(
                    f"{agent_id}:{run_id[0]}: no reconstructed cost and missing or inconsistent "
                    "reported_run_total_cost_usd (require one non-null total per agent/run)"
                )
        return errors
    return []


def _cost_provenance_warnings(provenance_values: list[str]) -> list[str]:
    warnings: list[str] = []
    if CostProvenance.AS_REPORTED_ONLY.value in provenance_values:
        warnings.append("cost provenance is as_reported_only")
    if CostProvenance.COST_NOT_AVAILABLE.value in provenance_values:
        warnings.append(
            "cost provenance is cost_not_available; cost-derived views will be suppressed"
        )
    if CostProvenance.PARTIAL.value in provenance_values:
        warnings.append("cost provenance is partial")
    return warnings


def _cost_provenance_check(
    provenance_values: list[str],
    errors: list[str],
    warnings: list[str],
) -> EvidenceCheck:
    details: dict[str, Json] = {"cost_provenance": _json_array(provenance_values)}
    if errors:
        details["errors"] = _json_array(sorted(errors))
        return _check(
            "cost_provenance_explicit",
            "error",
            "fail",
            f"cost provenance is incomplete or internally inconsistent: {sorted(errors)}",
            details,
        )
    if warnings:
        details["warnings"] = _json_array(sorted(warnings))
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
