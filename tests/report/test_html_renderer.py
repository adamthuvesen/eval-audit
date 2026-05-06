"""Tests for the optional static HTML report rendering."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from eval_audit.schema import StudySpec


def _byo_markdown(repo_root: Path) -> str:
    from eval_audit.checks import check_evidence
    from eval_audit.report.markdown import render_report
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "examples" / "byo-minimal" / "study.yaml")
    runs = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    readiness = check_evidence(study, runs, repo_root=repo_root)
    check_sha256 = hashlib.sha256(readiness.to_json_bytes()).hexdigest()
    result = analyze(study, runs, bootstrap_iterations=200, bootstrap_seed=42)
    return render_report(
        result,
        study,
        runs,
        clock=lambda: datetime(1970, 1, 1, tzinfo=UTC),
        git_commit="test",
        fixture_sha256="0" * 64,
        repo_root=repo_root,
        bootstrap_iterations=200,
        bootstrap_seed=42,
        evidence_readiness=readiness.status,
        check_sha256=check_sha256,
    )


def test_html_report__contains_markdown_sections_in_order(repo_root: Path) -> None:
    from eval_audit.report.html import render_html_report

    markdown = _byo_markdown(repo_root)
    html = render_html_report(markdown, title="BYO")

    expected = [
        "## Audit Summary",
        "## Study",
        "## Provenance",
        "## Per-agent summary",
        "## Claims",
        "## Robustness Review",
        "## Cost-quality view",
        "## Residual risks",
        "## Reproducibility footer",
    ]
    last = -1
    for section in expected:
        pos = html.find(section)
        assert pos != -1, section
        assert pos > last, section
        last = pos
    assert "`switch`" in html
    assert "report.md</code> is the canonical reproducibility artifact" in html


def test_html_report__output_is_deterministic(repo_root: Path) -> None:
    from eval_audit.report.html import render_html_report

    markdown = _byo_markdown(repo_root)
    first = render_html_report(markdown, title="BYO")
    second = render_html_report(markdown, title="BYO")

    assert hashlib.sha256(first.encode()).hexdigest() == hashlib.sha256(second.encode()).hexdigest()


def test_html_report__escapes_untrusted_report_text() -> None:
    from eval_audit.report.html import render_html_report

    markdown = '## Study\n\n- **claim:** <script>alert("x")</script> & "quoted"\n'
    html = render_html_report(markdown, title='Study <unsafe> "title"')

    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html
    assert "&amp;" in html
    assert "Study &lt;unsafe&gt; &quot;title&quot;" in html


def test_html_report__preserves_cost_provenance_caveat(repo_root: Path) -> None:
    from eval_audit.report.html import render_html_report

    markdown = (repo_root / "reports" / "tau-bench-airline-tool-calling" / "report.md").read_text()
    html = render_html_report(markdown, title="TAU")

    assert "Cost provenance caveat" in html
    assert "as_reported_only" in html


def test_html_report__preserves_copyable_summary_and_verdict_explainer(repo_root: Path) -> None:
    from eval_audit.report.html import render_html_report

    markdown = _byo_markdown(repo_root)
    html = render_html_report(markdown, title="BYO")

    assert "Copyable summary" in html
    assert "Verdict explainer" in html
    assert "report.md</code> is the canonical reproducibility artifact" in html


def test_html_report__not_written_when_markdown_rendering_refuses(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from typer.testing import CliRunner

    from eval_audit.cli import app

    frame = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    bad = frame.with_columns(
        pl.when(pl.col("agent_id") == "bob")
        .then(pl.lit("other-harness"))
        .otherwise(pl.col("harness"))
        .alias("harness")
    )
    bad_path = tmp_path / "cross-harness.parquet"
    bad.write_parquet(bad_path)

    out_dir = tmp_path / "reports"
    result = CliRunner().invoke(
        app,
        [
            "audit",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(bad_path),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
            "--bootstrap-iterations",
            "200",
            "--html",
        ],
    )

    assert result.exit_code != 0
    assert not (out_dir / "byo-minimal" / "report.html").exists()
