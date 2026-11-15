"""Report consistency with the settings that produced the analysis."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eval_audit.report import ReportContractError
from eval_audit.report.markdown import render_report
from eval_audit.stats import analyze
from tests.stats.test_sensitivity import _family


def test_report_uses_actual_analysis_settings_when_overrides_are_omitted(repo_root) -> None:
    study, runs = _family()
    result = analyze(study, runs, bootstrap_iterations=123, bootstrap_seed=7)
    text = render_report(
        result,
        study,
        runs,
        clock=lambda: datetime(2026, 11, 5, tzinfo=UTC),
        git_commit="settings-test",
        fixture_sha256="0" * 64,
        repo_root=repo_root,
    )
    assert "- **bootstrap_seed:** `7`" in text
    assert "- **bootstrap_iterations:** `123`" in text
    assert "- **alpha:** `0.05`" in text


@pytest.mark.parametrize("override", [{"bootstrap_seed": 42}, {"bootstrap_iterations": 10_000}])
def test_report_refuses_mismatched_analysis_settings(repo_root, override) -> None:
    study, runs = _family()
    result = analyze(study, runs, bootstrap_iterations=123, bootstrap_seed=7)
    with pytest.raises(ValueError, match="must match the analysis result"):
        render_report(
            result,
            study,
            runs,
            clock=lambda: datetime(2026, 11, 5, tzinfo=UTC),
            git_commit="settings-test",
            fixture_sha256="0" * 64,
            repo_root=repo_root,
            **override,
        )


@pytest.mark.parametrize(
    ("field", "actual", "expected"),
    [("study.id", "another-study", "stub"), ("inference.alpha", 0.1, 0.05)],
)
def test_report_refuses_a_study_that_disagrees_with_the_analysis(
    repo_root, field, actual, expected
) -> None:
    study, runs = _family()
    result = analyze(study, runs, bootstrap_iterations=123, bootstrap_seed=7)
    if field == "study.id":
        study.id = actual
    else:
        study.inference.alpha = actual
    with pytest.raises(ReportContractError) as exc_info:
        render_report(
            result,
            study,
            runs,
            clock=lambda: datetime(2026, 11, 5, tzinfo=UTC),
            git_commit="settings-test",
            fixture_sha256="0" * 64,
            repo_root=repo_root,
        )
    assert f"report {field} mismatch" in str(exc_info.value)
    assert f"expected {expected!r}" in str(exc_info.value)
    assert f"actual {actual!r}" in str(exc_info.value)
