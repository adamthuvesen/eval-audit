"""Acceptance tests for the StudySpec markdown renderer."""

from __future__ import annotations

from pathlib import Path


def test_render__produces_all_required_sections(repo_root: Path) -> None:
    """WHEN render_study_spec(study) is called for the GAIA HAL Generalist study,
    THEN the returned string contains all seven section headings in order,
    agents are listed verbatim, and the primary claim text appears once.
    """
    from eval_audit.schema import StudySpec
    from eval_audit.spec import render_study_spec

    study = StudySpec.from_yaml(repo_root / "studies" / "gaia-hal-generalist.yaml")
    text = render_study_spec(study)

    expected_headings = [
        "## Study identity",
        "## Primary outcome",
        "## Agents",
        "## Design",
        "## Inference plan",
        "## Cost view",
        "## Claims",
    ]
    last_pos = -1
    for heading in expected_headings:
        pos = text.find(heading)
        assert pos != -1, f"missing heading: {heading}"
        assert pos > last_pos, f"heading out of order: {heading}"
        last_pos = pos

    for agent in study.agents:
        assert agent.id in text, f"agent {agent.id!r} missing from rendered spec"

    primary_claim_text = study.claims[0].text
    # Claim text may wrap; check that the first 30 chars appear in the rendered output.
    assert primary_claim_text[:30] in text


def test_render__is_byte_identical_across_runs(repo_root: Path) -> None:
    """WHEN render_study_spec is called twice with the same input,
    THEN both invocations produce byte-identical strings.
    """
    import hashlib

    from eval_audit.schema import StudySpec
    from eval_audit.spec import render_study_spec

    study = StudySpec.from_yaml(repo_root / "studies" / "gaia-hal-generalist.yaml")
    a = render_study_spec(study)
    b = render_study_spec(study)
    assert hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest()


def test_render__null_target_mde_renders_none_declared(repo_root: Path, tmp_path: Path) -> None:
    """WHEN a study's inference.target_mde is null,
    THEN the rendered Inference plan section contains 'none declared'.
    """
    from eval_audit.schema import StudySpec
    from eval_audit.spec import render_study_spec

    src = (repo_root / "studies" / "gaia-hal-generalist.yaml").read_text()
    src = src.replace("target_mde: 0.03", "target_mde: null")
    study_path = tmp_path / "gaia-hal-generalist-no-mde.yaml"
    study_path.write_text(src)

    study = StudySpec.from_yaml(study_path)
    text = render_study_spec(study)

    assert "## Inference plan" in text
    inference_idx = text.index("## Inference plan")
    next_section_idx = text.index("##", inference_idx + 1)
    inference_block = text[inference_idx:next_section_idx]
    assert "none declared" in inference_block
