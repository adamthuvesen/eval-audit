"""Completed summary validation against actual audit output."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from eval_audit.schema.audit_summary import AuditSummary


@pytest.fixture(scope="module")
def summary_payload(repo_root: Path, tmp_path_factory: pytest.TempPathFactory) -> dict:
    from eval_audit.cli import app

    output = tmp_path_factory.mktemp("summary-integrity")
    result = CliRunner().invoke(
        app,
        [
            "audit",
            str(repo_root / "examples/byo-minimal/study.yaml"),
            "--runs",
            str(repo_root / "examples/byo-minimal/runs.parquet"),
            "--out-dir",
            str(output),
            "--repo-root",
            str(repo_root),
            "--bootstrap-iterations",
            "30",
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads((output / "byo-minimal/summary.json").read_text())


def test_actual_audit_summary_validates_and_round_trips(summary_payload: dict) -> None:
    summary = AuditSummary.model_validate(summary_payload)
    assert summary.model_dump(mode="json") == summary_payload


@pytest.mark.parametrize("version", [0, 2, True, 1.0, "1"])
def test_summary_rejects_invalid_version(summary_payload: dict, version: object) -> None:
    payload = copy.deepcopy(summary_payload)
    payload["schema_version"] = version
    with pytest.raises(ValidationError, match="schema_version"):
        AuditSummary.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("verdict", "almost_switch"),
        ("claim_status", "unknown"),
        ("readiness", "maybe_ready"),
        ("cost_provenance", "guessed"),
        ("paired_tasks", 0),
        ("paired_tasks", True),
        ("adjusted_p_value", 1.01),
        ("delta", 1.01),
        ("treatment_total_cost_usd", -1.0),
    ],
)
def test_summary_rejects_invalid_claim_domains(
    summary_payload: dict, field: str, value: object
) -> None:
    payload = copy.deepcopy(summary_payload)
    payload["claims"][0][field] = value
    with pytest.raises(ValidationError, match=field):
        AuditSummary.model_validate(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "field", ["delta", "ci_low", "ci_high", "adjusted_p_value", "treatment_total_cost_usd"]
)
def test_summary_rejects_nonfinite_claim_numbers(
    summary_payload: dict, field: str, value: float
) -> None:
    payload = copy.deepcopy(summary_payload)
    payload["claims"][0][field] = value
    with pytest.raises(ValidationError, match=field):
        AuditSummary.model_validate(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_summary_rejects_nonfinite_explanation_conditions(
    summary_payload: dict, value: float
) -> None:
    payload = copy.deepcopy(summary_payload)
    payload["claims"][0]["verdict_explanation"]["conditions"]["delta_ci_low"] = value
    with pytest.raises(ValidationError, match="conditions"):
        AuditSummary.model_validate(payload)


@pytest.mark.parametrize(
    "defect", ["duplicate", "study", "readiness", "artifacts", "verdict", "ci", "self"]
)
def test_summary_rejects_inconsistent_claim_fields(summary_payload: dict, defect: str) -> None:
    payload = copy.deepcopy(summary_payload)
    claim = payload["claims"][0]
    if defect == "duplicate":
        payload["claims"].append(copy.deepcopy(claim))
    elif defect == "study":
        claim["study_id"] = "another-study"
    elif defect == "readiness":
        claim["readiness"] = "not_ready"
    elif defect == "artifacts":
        claim["artifact_hashes"]["report_md"] = "0" * 64
    elif defect == "verdict":
        claim["verdict_explanation"]["verdict"] = "hold"
    elif defect == "ci":
        claim["ci_low"], claim["ci_high"] = 0.9, -0.9
    elif defect == "self":
        claim["treatment"] = claim["control"]
    with pytest.raises(ValidationError):
        AuditSummary.model_validate(payload)


def test_summary_rejects_cost_values_when_cost_is_unavailable(summary_payload: dict) -> None:
    payload = copy.deepcopy(summary_payload)
    payload["claims"][0]["cost_provenance"] = "cost_not_available"
    with pytest.raises(ValidationError, match="null claim costs"):
        AuditSummary.model_validate(payload)
