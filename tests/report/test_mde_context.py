"""Acceptance tests for the MDE context column + paragraph in the analysis report."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def _render_for_study(study_yaml: Path, repo_root: Path) -> str:
    from rigor.ingest.hal_gaia import HalGaiaAdapter
    from rigor.report.markdown import render_report
    from rigor.schema import StudySpec
    from rigor.stats import analyze

    study = StudySpec.from_yaml(study_yaml)
    adapter = HalGaiaAdapter()
    runs = adapter.load(repo_root / "scouting" / "candidates" / "gaia")
    result = analyze(study, runs, bootstrap_iterations=2_000, bootstrap_seed=42)
    return render_report(
        result,
        study,
        runs,
        clock=lambda: datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC),
        git_commit="snapshot",
        fixture_sha256="0" * 64,
        repo_root=repo_root,
        bootstrap_iterations=2_000,
        bootstrap_seed=42,
    )


def test_mde__target_mde_set_renders_column_and_paragraph(repo_root: Path) -> None:
    """WHEN the renderer is called with a study whose inference.target_mde is 0.03,
    THEN the rendered ## Claims table includes a target_mde column AND an
    'MDE context' paragraph appears immediately after the table.
    """
    text = _render_for_study(repo_root / "studies" / "exhibit-a.yaml", repo_root)

    claims_idx = text.index("## Claims")
    cost_idx = text.index("## Cost-quality view")
    claims_block = text[claims_idx:cost_idx]

    # target_mde column header in the claims table.
    assert "target_mde" in claims_block
    # The Exhibit A target_mde is 0.03 = 3.00 pp.
    assert "+3.00 pp" in claims_block
    # MDE context paragraph between the table and the next section.
    assert "MDE context" in claims_block


def test_mde__target_mde_null_omits_column_and_paragraph(repo_root: Path, tmp_path: Path) -> None:
    """WHEN the renderer is called with a study whose inference.target_mde is None,
    THEN the ## Claims table does NOT include a target_mde column AND no
    'MDE context' paragraph appears between the ## Claims table and the
    ## Cost-quality view heading.
    """
    src = (repo_root / "studies" / "exhibit-a.yaml").read_text()
    src = src.replace("target_mde: 0.03", "target_mde: null")
    no_mde_yaml = tmp_path / "exhibit-a-no-mde.yaml"
    no_mde_yaml.write_text(src)

    text = _render_for_study(no_mde_yaml, repo_root)

    claims_idx = text.index("## Claims")
    cost_idx = text.index("## Cost-quality view")
    claims_block = text[claims_idx:cost_idx]

    assert "target_mde" not in claims_block
    assert "MDE context" not in claims_block
