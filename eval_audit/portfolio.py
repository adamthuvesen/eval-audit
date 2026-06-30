"""Audit portfolio/evidence-index rendering from completed summary artifacts."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from eval_audit.report.summary import file_sha256
from eval_audit.schema.audit_summary import AuditSummary

REQUIRED_CLAIM_TEXT_FIELDS: tuple[str, ...] = (
    "study_id",
    "claim_id",
    "treatment",
    "control",
    "verdict",
    "readiness",
    "cost_provenance",
)
REQUIRED_CLAIM_NUMERIC_FIELDS: tuple[str, ...] = ("delta", "ci_low", "ci_high")


@dataclass(frozen=True)
class PortfolioRow:
    study_id: str
    claim_id: str | None
    treatment: str | None
    control: str | None
    verdict: str | None
    readiness: str | None
    delta: float | None
    ci_low: float | None
    ci_high: float | None
    cost_provenance: str | None
    artifact_status: str
    report_dir: str
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "claim_id": self.claim_id,
            "treatment": self.treatment,
            "control": self.control,
            "verdict": self.verdict,
            "readiness": self.readiness,
            "delta": self.delta,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "cost_provenance": self.cost_provenance,
            "artifact_status": self.artifact_status,
            "report_dir": self.report_dir,
            "note": self.note,
        }


class _PortfolioSummaryError(ValueError):
    def __init__(self, status: str, note: str) -> None:
        super().__init__(note)
        self.status = status
        self.note = note


def _candidate_report_dirs(reports_dir: Path) -> list[Path]:
    if (reports_dir / "summary.json").exists():
        return [reports_dir]
    if not reports_dir.exists() or not reports_dir.is_dir():
        return []
    return sorted(path for path in reports_dir.iterdir() if path.is_dir())


def _incomplete_row(report_dir: Path, status: str, note: str) -> PortfolioRow:
    return PortfolioRow(
        study_id=report_dir.name,
        claim_id=None,
        treatment=None,
        control=None,
        verdict=None,
        readiness=None,
        delta=None,
        ci_low=None,
        ci_high=None,
        cost_provenance=None,
        artifact_status=status,
        report_dir=str(report_dir),
        note=note,
    )


def _staleness_note(report_dir: Path, payload: dict[str, Any]) -> str | None:
    hashes = payload.get("artifact_hashes")
    paths = payload.get("artifact_paths")
    if not isinstance(hashes, dict) or not isinstance(paths, dict):
        return "summary.json lacks artifact paths or hashes"
    for path_key, hash_key in (
        ("check_json", "check_json"),
        ("analysis_json", "analysis_json"),
        ("report_md", "report_md"),
    ):
        artifact_name = paths.get(path_key)
        expected_hash = hashes.get(hash_key)
        if not isinstance(artifact_name, str) or not isinstance(expected_hash, str):
            return f"summary.json lacks {path_key} hash"
        artifact = report_dir / artifact_name
        if not artifact.exists():
            return f"{artifact_name} is missing"
        actual_hash = file_sha256(artifact)
        if actual_hash != expected_hash:
            return f"{artifact_name} hash differs from summary.json"
    return None


def _required_text(claim: dict[str, Any], key: str) -> str:
    value = claim[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_finite_float(claim: dict[str, Any], key: str) -> float:
    value = claim[key]
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a finite number")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{key} must be a finite number")
    return converted


def _complete_claim_row(report_dir: Path, claim: object) -> PortfolioRow:
    if not isinstance(claim, dict):
        raise ValueError("claim record is not an object")
    for key in REQUIRED_CLAIM_TEXT_FIELDS:
        _required_text(claim, key)
    numeric_fields = {
        key: _required_finite_float(claim, key) for key in REQUIRED_CLAIM_NUMERIC_FIELDS
    }
    return PortfolioRow(
        study_id=claim["study_id"],
        claim_id=claim["claim_id"],
        treatment=claim["treatment"],
        control=claim["control"],
        verdict=claim["verdict"],
        readiness=claim["readiness"],
        delta=numeric_fields["delta"],
        ci_low=numeric_fields["ci_low"],
        ci_high=numeric_fields["ci_high"],
        cost_provenance=claim["cost_provenance"],
        artifact_status="complete",
        report_dir=str(report_dir),
        note=str(claim.get("cost_caveat", "")),
    )


def _has_partial_artifacts(report_dir: Path) -> bool:
    return any(
        (report_dir / name).exists() for name in ("report.md", "analysis.json", "check.json")
    )


def _validated_summary_payload(report_dir: Path) -> dict[str, Any]:
    summary_path = report_dir / "summary.json"
    try:
        raw_payload = json.loads(summary_path.read_text())
    except json.JSONDecodeError as exc:
        raise _PortfolioSummaryError("invalid_summary", str(exc)) from exc
    if not isinstance(raw_payload, dict):
        raise _PortfolioSummaryError("invalid_summary", "summary.json root must be an object")
    try:
        payload = AuditSummary.model_validate(raw_payload).to_json_dict()
    except (ValidationError, ValueError, TypeError) as exc:
        raise _PortfolioSummaryError("invalid_summary", str(exc)) from exc
    if stale_note := _staleness_note(report_dir, payload):
        raise _PortfolioSummaryError("stale_summary", stale_note)
    return payload


def _complete_claim_rows(report_dir: Path, claims: object) -> list[PortfolioRow]:
    if not isinstance(claims, list) or not claims:
        raise _PortfolioSummaryError("invalid_summary", "summary.json has no claim records")
    try:
        return [_complete_claim_row(report_dir, claim) for claim in claims]
    except (KeyError, TypeError, ValueError) as exc:
        raise _PortfolioSummaryError(
            "invalid_summary",
            f"summary.json has invalid claim record: {exc}",
        ) from exc


def _report_dir_rows(report_dir: Path) -> list[PortfolioRow]:
    summary_path = report_dir / "summary.json"
    if not summary_path.exists():
        if _has_partial_artifacts(report_dir):
            return [_incomplete_row(report_dir, "missing_summary", "summary.json is missing")]
        return []
    try:
        payload = _validated_summary_payload(report_dir)
        return _complete_claim_rows(report_dir, payload.get("claims"))
    except _PortfolioSummaryError as exc:
        return [_incomplete_row(report_dir, exc.status, exc.note)]


def load_portfolio_rows(reports_dir: Path) -> list[PortfolioRow]:
    rows: list[PortfolioRow] = []
    for report_dir in _candidate_report_dirs(reports_dir):
        rows.extend(_report_dir_rows(report_dir))
    return sorted(
        rows,
        key=lambda row: (
            row.study_id,
            row.claim_id or "",
            row.artifact_status,
        ),
    )


def portfolio_json_bytes(rows: list[PortfolioRow]) -> bytes:
    payload = {"schema_version": 1, "rows": [row.as_dict() for row in rows]}
    return (json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n").encode()


def _format_pp(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:+.2f} pp"


def _format_ci(row: PortfolioRow) -> str:
    if row.ci_low is None or row.ci_high is None:
        return "n/a"
    return f"[{_format_pp(row.ci_low)}, {_format_pp(row.ci_high)}]"


def _markdown_row(row: PortfolioRow) -> str:
    return (
        f"| {row.study_id} | {row.claim_id or 'n/a'} | {row.treatment or 'n/a'} | "
        f"{row.control or 'n/a'} | {row.verdict or 'n/a'} | {row.readiness or 'n/a'} | "
        f"{_format_pp(row.delta)} | {_format_ci(row)} | {row.cost_provenance or 'n/a'} | "
        f"{row.artifact_status} |"
    )


def render_portfolio_markdown(rows: list[PortfolioRow], reports_dir: Path) -> str:
    parts = [
        "# Audit Portfolio",
        "",
        (
            "Evidence index for declared audits. Rows are only comparable within "
            "their declared study and harness context; this is not a universal model ordering."
        ),
        "",
        f"- **reports_dir:** `{reports_dir}`",
        "",
        "| study_id | claim_id | treatment | control | verdict | readiness | delta | CI | cost_provenance | artifact_status |",
        "|---|---|---|---|---|---|---:|---|---|---|",
    ]
    for row in rows:
        parts.append(_markdown_row(row))
    incomplete = [row for row in rows if row.artifact_status != "complete"]
    if incomplete:
        parts.extend(["", "## Incomplete Artifacts", ""])
        for row in incomplete:
            parts.append(f"- `{row.report_dir}`: {row.artifact_status} — {row.note}")
    parts.append("")
    return "\n".join(parts)
