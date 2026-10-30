"""Audit publication failure and containment checks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eval_audit.artifacts import (
    INCOMPLETE_MARKER,
    ArtifactError,
    audit_directory,
    publish_artifacts,
)
from eval_audit.portfolio import load_portfolio_rows
from eval_audit.schema.artifacts import STAGING_PREFIX


@pytest.fixture
def completed_audit(repo_root: Path, tmp_path: Path) -> Path:
    from eval_audit.cli import app

    output = tmp_path / "reports"
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
            "--html",
        ],
    )
    assert result.exit_code == 0, result.output
    directory = output / "byo-minimal"
    assert all(row.artifact_status == "complete" for row in load_portfolio_rows(directory))
    return directory


@pytest.mark.parametrize("failure_site", ["stage", "publish", "cleanup"])
def test_failed_publication_preserves_previous_complete_audit(
    completed_audit: Path, monkeypatch: pytest.MonkeyPatch, failure_site: str
) -> None:
    previous = {path.name: path.read_bytes() for path in completed_audit.iterdir()}
    replacement = {name: b"replacement:" + content for name, content in previous.items()}
    replacement.pop("report.html")
    injected = False
    original_replace = os.replace
    original_write_bytes = Path.write_bytes
    original_unlink = Path.unlink
    replacements = 0

    def fail_replace(source: Path, destination: Path) -> None:
        nonlocal injected, replacements
        replacements += 1
        if failure_site == "publish" and replacements == 2:
            injected = True
            raise OSError("injected publication failure")
        original_replace(source, destination)

    def fail_write_bytes(path: Path, content: bytes) -> int:
        nonlocal injected
        if failure_site == "stage" and not injected and path.parent.name.startswith(STAGING_PREFIX):
            injected = True
            raise OSError("injected staging failure")
        return original_write_bytes(path, content)

    def fail_unlink(path: Path, missing_ok: bool = False) -> None:
        nonlocal injected
        if failure_site == "cleanup" and not injected and path == completed_audit / "report.html":
            injected = True
            raise OSError("injected cleanup failure")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(os, "replace", fail_replace)
    monkeypatch.setattr(Path, "write_bytes", fail_write_bytes)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(OSError, match="injected"):
        publish_artifacts(completed_audit, replacement, complete=True)
    assert injected
    assert previous == {path.name: path.read_bytes() for path in completed_audit.iterdir()}
    assert all(row.artifact_status == "complete" for row in load_portfolio_rows(completed_audit))


def test_interrupted_publication_is_not_reported_as_a_complete_portfolio(
    completed_audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_replace = os.replace
    previous_summary = (completed_audit / "summary.json").read_bytes()

    def interrupt_after_replace(source: Path, destination: Path) -> None:
        original_replace(source, destination)
        raise KeyboardInterrupt("injected process interruption")

    monkeypatch.setattr(os, "replace", interrupt_after_replace)
    with pytest.raises(KeyboardInterrupt):
        publish_artifacts(
            completed_audit,
            {"check.json": b"new generation", "summary.json": b"new summary"},
            complete=True,
        )
    assert (completed_audit / INCOMPLETE_MARKER).exists()
    assert (completed_audit / "summary.json").read_bytes() == previous_summary
    rows = load_portfolio_rows(completed_audit)
    assert len(rows) == 1
    assert rows[0].artifact_status == "incomplete_publication"
    assert rows[0].verdict is None


def test_audit_directory_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "reports"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escaped").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactError, match="escapes output root"):
        audit_directory(root, "escaped")
    assert not list(outside.iterdir())


def test_publication_rejects_artifact_symlink_without_changing_target(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    directory.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"keep this file")
    (directory / "summary.json").symlink_to(outside)
    with pytest.raises(ArtifactError, match="regular file"):
        publish_artifacts(directory, {"summary.json": b"replacement"}, complete=True)
    assert outside.read_bytes() == b"keep this file"
    assert not (directory / INCOMPLETE_MARKER).exists()


def test_successful_publication_preserves_unowned_files(completed_audit: Path) -> None:
    user_file = completed_audit / "review-notes.txt"
    user_file.write_text("review notes")
    artifacts = {
        path.name: path.read_bytes()
        for path in completed_audit.iterdir()
        if path.name != user_file.name
    }
    publish_artifacts(completed_audit, artifacts, complete=True)
    assert user_file.read_text() == "review notes"
    assert not (completed_audit / INCOMPLETE_MARKER).exists()


def test_competing_writer_is_rejected_before_artifact_changes(completed_audit: Path) -> None:
    from eval_audit.artifacts import _publication_lock

    previous = {path.name: path.read_bytes() for path in completed_audit.iterdir()}
    with (
        _publication_lock(completed_audit),
        pytest.raises(ArtifactError, match="another writer"),
    ):
        publish_artifacts(completed_audit, {"summary.json": b"new generation"}, complete=True)
    assert previous == {path.name: path.read_bytes() for path in completed_audit.iterdir()}


@pytest.mark.parametrize("study_id", [".audit-stage-", ".audit-stage-user"])
def test_audit_directory_rejects_reserved_staging_namespace(tmp_path: Path, study_id: str) -> None:
    root = tmp_path / "reports"
    with pytest.raises(ArtifactError, match="reserved staging prefix"):
        audit_directory(root, study_id)
    assert not root.exists()
