"""Application workflow from validated evidence to prepared audit artifacts."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import polars as pl

from eval_audit.checks import (
    ReadinessCheck,
    ReadinessResult,
    ReadinessStatus,
    check_evidence,
    check_prepared_evidence,
)
from eval_audit.evidence import prepare_evidence
from eval_audit.evidence_types import EvidenceSource
from eval_audit.fixtures import benchmark_dir_name
from eval_audit.ingest import IngestAdapter, IngestContractError
from eval_audit.ingest.generic import load_run_records
from eval_audit.ingest.hal_gaia import HalGaiaAdapter
from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter
from eval_audit.ingest.swe_bench_verified import SweBenchVerifiedAdapter
from eval_audit.ingest.synthetic import SyntheticAdapter
from eval_audit.ingest.terminal_bench import TerminalBenchMuxAdapter
from eval_audit.report.decisions import DECISION_IMPACT_VOCAB, decision_impact
from eval_audit.report.html import render_html_report
from eval_audit.report.markdown import render_report
from eval_audit.report.presentation import resolve_study_presentation
from eval_audit.report.sensitivity import claim_context_for_result
from eval_audit.report.summary import build_audit_summary, summary_json_bytes
from eval_audit.schema import StudySpec
from eval_audit.schema.artifacts import ARTIFACT_FILES
from eval_audit.stats import AnalysisResult, analyze
from eval_audit.stats.analyze import analyze_prepared
from eval_audit.stats.results import AnalysisSettings


@dataclass(frozen=True)
class AuditProducts:
    result: AnalysisResult
    readiness: ReadinessResult
    artifacts: dict[str, bytes]


def serialise_result(result: AnalysisResult) -> dict[str, Any]:
    out = dataclasses.asdict(result)
    out["pareto_frontier"] = sorted(result.pareto_frontier)
    out["bootstrap_seed"] = result.bootstrap_seed
    return out


def analysis_json_bytes(result: AnalysisResult) -> bytes:
    return (json.dumps(serialise_result(result), allow_nan=False, indent=2) + "\n").encode()


def claim_verdicts(result: AnalysisResult, study: StudySpec) -> list[dict[str, str]]:
    return [
        {
            "claim_id": claim.claim_id,
            "verdict": decision_impact(claim_context_for_result(claim, result, study)),
        }
        for claim in result.claims
    ]


def build_audit(
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    study_path: Path,
    source: EvidenceSource,
    repo_root: Path,
    bootstrap_iterations: int,
    bootstrap_seed: int,
    git_commit: str,
    html: bool = False,
) -> AuditProducts:
    """Complete validation, inference, and rendering before any output is written."""
    evidence = prepare_evidence(study, runs)
    study, runs = evidence.study, evidence.runs
    initial_checks = [
        ReadinessCheck(
            "study_loads", "error", "pass", "study YAML loaded", {"path": str(study_path)}, None
        ),
        ReadinessCheck(
            "runs_load",
            "error",
            "pass",
            "runs parquet loaded",
            {"path": source.display_path(repo_root), "rows": runs.height},
            None,
        ),
    ]
    readiness = check_prepared_evidence(
        evidence, repo_root=repo_root, initial_checks=initial_checks, source=source
    )
    result = analyze_prepared(
        evidence,
        settings=AnalysisSettings(
            alpha=study.inference.alpha,
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed=bootstrap_seed,
        ),
    )
    check_bytes = readiness.to_json_bytes()
    markdown = render_report(
        result,
        study,
        runs,
        clock=lambda: datetime(1970, 1, 1, tzinfo=UTC),
        git_commit=git_commit,
        fixture_sha256=source.fixture_sha256,
        repo_root=repo_root,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
        evidence_readiness=readiness.status,
        check_sha256=hashlib.sha256(check_bytes).hexdigest(),
        source=source,
    )
    artifacts = {
        "check.json": check_bytes,
        "analysis.json": analysis_json_bytes(result),
        "report.md": markdown.encode(),
    }
    if html:
        artifacts["report.html"] = render_html_report(
            markdown, title=f"{study.id} audit report"
        ).encode()
    presentation = resolve_study_presentation(study, runs, result, repo_root, source)
    summary = build_audit_summary(
        result=result,
        study=study,
        runs=runs,
        presentation=presentation,
        readiness=readiness.status,
        artifact_paths={
            key: Path(name) for key, name in ARTIFACT_FILES.items() if name in artifacts
        },
        artifact_bytes={
            key: artifacts[name] for key, name in ARTIFACT_FILES.items() if name in artifacts
        },
    )
    artifacts["summary.json"] = summary_json_bytes(summary)
    return AuditProducts(result, readiness, artifacts)


ADAPTERS: dict[str, Callable[[], IngestAdapter]] = {
    "gaia": HalGaiaAdapter,
    "synthetic": SyntheticAdapter,
    "tau_bench": HalTauBenchAdapter,
    "swe-bench-verified": SweBenchVerifiedAdapter,
    "terminal-bench-2": TerminalBenchMuxAdapter,
}

# Benchmarks whose committed fixture lives under `examples/<study.id>/` rather
# than `scouting/candidates/<benchmark>/`. Public-submission re-analyses ship
# their canonical RunRecord parquet inside the repo (see scouting-fixtures
# capability spec) because the upstream artifacts (e.g. S3-hosted submission
# logs) are not committed.
_EXAMPLES_BACKED_BENCHMARKS: frozenset[str] = frozenset({"swe-bench-verified", "terminal-bench-2"})

_READINESS_RANK: dict[ReadinessStatus, int] = {
    "not_ready": 0,
    "ready_with_warnings": 1,
    "ready": 2,
}


class UnsupportedBenchmarkError(ValueError):
    pass


def _fixture_dir_and_parquet(study: StudySpec, repo_root: Path) -> tuple[Path, Path]:
    if study.benchmark not in ADAPTERS:
        raise UnsupportedBenchmarkError(
            f"no benchmark-keyed ingest adapter for benchmark={study.benchmark!r}. "
            "Pass --runs PATH for canonical BYO RunRecord parquet, or use one "
            f"of the adapter-backed benchmarks: {sorted(ADAPTERS)}"
        )
    if study.benchmark == "synthetic":
        source = repo_root / "scouting" / "synthetic"
        return source, source / "runs.parquet"
    if study.benchmark in _EXAMPLES_BACKED_BENCHMARKS:
        source = repo_root / "examples" / study.id
        return source, source / "runs.parquet"
    source = repo_root / "scouting" / "candidates" / benchmark_dir_name(study.benchmark)
    return source, source / "sample.parquet"


def load_evidence(
    study: StudySpec, repo_root: Path, runs_override: Path | None
) -> tuple[pl.DataFrame, EvidenceSource]:
    """Load canonical rows from --runs, or from the benchmark's committed adapter fixture."""
    if runs_override is not None:
        if not runs_override.is_file():
            raise IngestContractError(f"runs parquet must be a readable file: {runs_override}")
        source = EvidenceSource.from_path(runs_override, source_kind="canonical")
        frame = load_run_records(runs_override)
    else:
        source_dir, parquet_path = _fixture_dir_and_parquet(study, repo_root)
        source = EvidenceSource.from_path(
            parquet_path, source_kind="adapter", source_dir=source_dir
        )
        frame = ADAPTERS[study.benchmark]().load(source_dir)
    if (
        EvidenceSource.from_path(source.fixture_path, source_kind=source.source_kind).fixture_sha256
        != source.fixture_sha256
    ):
        raise IngestContractError(
            f"runs changed while loading: {source.fixture_path}; retry with a stable input file"
        )
    return frame, source


def _readiness_gate_failures(
    readiness: ReadinessResult,
    min_readiness: ReadinessStatus,
) -> list[dict[str, object]]:
    if readiness.status == "not_ready":
        return [
            {
                "type": "readiness",
                "check_id": check.id,
                "severity": check.severity,
                "message": check.message,
                "fix_suggestion": check.fix_suggestion,
            }
            for check in readiness.checks
            if check.status == "fail"
        ]
    if _READINESS_RANK[readiness.status] < _READINESS_RANK[min_readiness]:
        return [
            {
                "type": "readiness",
                "message": (f"readiness {readiness.status} does not meet minimum {min_readiness}"),
            }
        ]
    return []


def gate(
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    source: EvidenceSource,
    repo_root: Path,
    min_readiness: ReadinessStatus,
    allowed_verdicts: list[str],
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> dict[str, object]:
    """Gate evidence readiness, then claim verdicts; analysis runs only on ready-enough evidence."""
    readiness = check_evidence(study, runs, repo_root=repo_root, source=source)
    claims: list[dict[str, str]] = []
    failures = _readiness_gate_failures(readiness, min_readiness)
    if not failures:
        result = analyze(
            study,
            runs,
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed=bootstrap_seed,
        )
        claims = claim_verdicts(result, study)
        failures = [
            {
                "type": "verdict",
                "claim_id": claim["claim_id"],
                "verdict": claim["verdict"],
                "allowed_verdicts": allowed_verdicts,
            }
            for claim in claims
            if claim["verdict"] not in allowed_verdicts
        ]
    return {
        "study_id": study.id,
        "status": "fail" if failures else "pass",
        "readiness": readiness.status,
        "allowed_verdicts": allowed_verdicts,
        "claims": claims,
        "failures": failures,
    }


class GateOptionError(ValueError):
    """Raised when a gate option is outside its allowed values."""


def validated_min_readiness(value: str) -> ReadinessStatus:
    if value not in {"ready", "ready_with_warnings"}:
        raise GateOptionError("--min-readiness must be one of: ready, ready_with_warnings")
    return cast(ReadinessStatus, value)


def allowed_gate_verdicts(allow_verdict: list[str] | None) -> list[str]:
    requested_verdicts = list(allow_verdict or DECISION_IMPACT_VOCAB)
    unknown = sorted(set(requested_verdicts) - set(DECISION_IMPACT_VOCAB))
    if unknown:
        raise GateOptionError(
            "unsupported verdict name(s): "
            f"{', '.join(unknown)}. Controlled vocabulary: "
            f"{', '.join(DECISION_IMPACT_VOCAB)}"
        )
    return requested_verdicts


def gate_output_text(payload: dict[str, object], *, json_output: bool) -> str:
    if json_output:
        return json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n"

    lines = [
        f"gate {payload['status']}: study={payload['study_id']} readiness={payload['readiness']}"
    ]
    claims = payload["claims"]
    failures = payload["failures"]
    if isinstance(claims, list):
        for claim in claims:
            lines.append(f"claim {claim['claim_id']}: {claim['verdict']}")
    if isinstance(failures, list):
        for failure in failures:
            if failure["type"] == "verdict":
                lines.append(
                    "failure: claim "
                    f"{failure['claim_id']} verdict {failure['verdict']} "
                    "not in allowed verdicts "
                    f"{', '.join(failure['allowed_verdicts'])}"
                )
            elif "check_id" in failure:
                lines.append(
                    f"failure: {failure['check_id']}: "
                    f"{failure['message']}; fix: {failure['fix_suggestion']}"
                )
            else:
                lines.append(f"failure: {failure['message']}")
    return "\n".join(lines) + "\n"
