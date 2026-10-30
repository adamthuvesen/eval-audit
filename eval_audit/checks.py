"""Audit-readiness checks for declared eval-audit evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import ValidationError
from yaml import YAMLError

from eval_audit.evidence import EvidenceCheck, Json, PreparedEvidence, inspect_evidence
from eval_audit.ingest import IngestContractError
from eval_audit.ingest.generic import load_run_records
from eval_audit.report.provenance import EvidenceSource
from eval_audit.schema import StudySpec
from eval_audit.schema.enums import ReadinessStatus
from eval_audit.scouting_paths import resolve_evidence_decision_doc

CheckSeverity = Literal["error", "warning", "info"]
CheckStatus = Literal["pass", "fail"]


_STATIC_FIX_SUGGESTIONS = {
    "study_loads": (
        "Fix the study YAML path or schema errors so StudySpec.from_yaml() "
        "can load the declared audit."
    ),
    "runs_load": (
        "Provide a readable canonical RunRecord parquet with the required task-level columns."
    ),
    "claim_agents_present": (
        "Add run rows for every treatment and control agent named by each "
        "claim, or update the study claims to reference agents present in the runs."
    ),
    "claimed_rows_match_study_harness": (
        "Cross-harness comparisons are not audit-ready; prepare a single-harness "
        "paired comparison that matches study.harness, or split the evidence into "
        "separate declared studies per harness."
    ),
    "paired_tasks_complete": (
        "Add the missing paired task rows, remove duplicate task/run rows, "
        "and make every claimed agent match design.observed_runs_per_agent "
        "for each task id."
    ),
    "outcome_supported": (
        "Declare a v0-supported success_rate, higher_is_better outcome for "
        "the study and every claim, or add metric-specific engine support first."
    ),
    "target_mde_declared": (
        "Declare inference.target_mde in the study YAML so the report can "
        "judge whether the paired evidence resolves the practical effect size."
    ),
    "residual_risks_source": (
        "Add or restore the scouting decision document that records residual "
        "risks and provenance notes for this fixture."
    ),
}


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
        return json.dumps(self.to_dict(), allow_nan=False, indent=2, sort_keys=True) + "\n"

    def to_json_bytes(self) -> bytes:
        return self.to_json().encode()


def readiness_from_diagnostics(
    study_id: str | None, diagnostics: tuple[EvidenceCheck, ...]
) -> ReadinessResult:
    return _result(
        study_id,
        [
            _check(item.id, item.severity, item.status, item.message, item.details)
            for item in diagnostics
        ],
    )


def render_readiness_text(result: ReadinessResult) -> str:
    errors = _count_failed_checks(result.checks, "error")
    warnings = _count_failed_checks(result.checks, "warning")
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
    except (FileNotFoundError, ValidationError, ValueError, YAMLError) as exc:
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
        source=EvidenceSource.from_path(runs_parquet, source_kind="canonical"),
    )


def check_loaded_evidence(
    study_yaml: Path,
    runs_parquet: Path,
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    repo_root: Path,
    initial_checks: list[ReadinessCheck] | None = None,
    source: EvidenceSource | None = None,
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
    return check_evidence(study, runs, repo_root=repo_root, initial_checks=checks, source=source)


def check_evidence(
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    repo_root: Path,
    initial_checks: list[ReadinessCheck] | None = None,
    source: EvidenceSource | None = None,
) -> ReadinessResult:
    return _readiness_for_diagnostics(
        study,
        runs,
        inspect_evidence(study, runs),
        repo_root=repo_root,
        initial_checks=initial_checks,
        source=source,
    )


def check_prepared_evidence(
    evidence: PreparedEvidence,
    *,
    repo_root: Path,
    initial_checks: list[ReadinessCheck] | None = None,
    source: EvidenceSource | None = None,
) -> ReadinessResult:
    """Render readiness checks from evidence that already passed preparation."""
    return _readiness_for_diagnostics(
        evidence.study,
        evidence.runs,
        evidence.diagnostics,
        repo_root=repo_root,
        initial_checks=initial_checks,
        source=source,
    )


def _readiness_for_diagnostics(
    study: StudySpec,
    runs: pl.DataFrame,
    diagnostics: tuple[EvidenceCheck, ...],
    *,
    repo_root: Path,
    initial_checks: list[ReadinessCheck] | None,
    source: EvidenceSource | None,
) -> ReadinessResult:
    checks: list[ReadinessCheck] = list(initial_checks) if initial_checks is not None else []
    if initial_checks is None:
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

    for diagnostic in diagnostics:
        checks = [check for check in checks if check.id != diagnostic.id]
        checks.append(
            _check(
                diagnostic.id,
                diagnostic.severity,
                diagnostic.status,
                diagnostic.message,
                diagnostic.details,
            )
        )
    if any(check.id in {"study_loads", "runs_load"} and check.status == "fail" for check in checks):
        return _result(study.id, checks)
    checks.append(_target_mde_declared(study))
    checks.append(_residual_risks_source(study, repo_root, source))
    return _result(study.id, checks)


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


def _residual_risks_source(
    study: StudySpec, repo_root: Path, source: EvidenceSource | None
) -> ReadinessCheck:
    decision = resolve_evidence_decision_doc(repo_root, study, source)
    if decision is None:
        return _check(
            "residual_risks_source",
            "warning",
            "fail",
            "no residual-risk/scouting decision document bound to this evidence",
            {"path": "not supplied with this evidence"},
        )
    path, label = decision
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
    if check_id == "cost_provenance_explicit":
        return _cost_provenance_fix_suggestion(details)
    if suggestion := _STATIC_FIX_SUGGESTIONS.get(check_id):
        return suggestion
    return "Repair the failed readiness condition before running analysis or rendering a report."


def _cost_provenance_fix_suggestion(details: dict[str, Json]) -> str:
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


def _result(study_id: str | None, checks: list[ReadinessCheck]) -> ReadinessResult:
    if _count_failed_checks(checks, "error") > 0:
        status: ReadinessStatus = "not_ready"
    elif _count_failed_checks(checks, "warning") > 0:
        status = "ready_with_warnings"
    else:
        status = "ready"
    return ReadinessResult(study_id=study_id, status=status, checks=checks)


def _count_failed_checks(checks: list[ReadinessCheck], severity: CheckSeverity) -> int:
    return sum(1 for check in checks if check.severity == severity and check.status == "fail")
