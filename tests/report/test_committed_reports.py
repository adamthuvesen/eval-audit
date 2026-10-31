"""Committed `reports/<id>/` artifacts match a fresh render from committed evidence.

`reports/` is the only copy of each rendered report. Only the `git_commit` value may
differ, because it records the commit that produced the file. The `summary.json` hashes of
`report.md` and `report.html` follow from that value, so they must match the committed files.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from eval_audit.cli import app

# report id -> CLI arguments that regenerate reports/<id>/ from the repo root.
REPORT_COMMANDS = {
    "byo-minimal": "audit examples/byo-minimal/study.yaml --runs examples/byo-minimal/runs.parquet --html",
    "decision-gallery": "report studies/decision-gallery.yaml --runs examples/decision-gallery/runs.parquet",
    "gaia-hal-generalist": "report studies/gaia-hal-generalist.yaml",
    "humaneval-direct-completion": "report studies/humaneval-direct-completion.yaml --runs examples/humaneval-direct-completion/runs.parquet",
    "swe-bench-verified-openhands": "report studies/swe-bench-verified-openhands.yaml",
    "tau-bench-airline-tool-calling": "report studies/tau-bench-airline-tool-calling.yaml",
    "terminal-bench-2-mux": "report studies/terminal-bench-2-mux.yaml",
}
GIT_COMMIT_LINE = re.compile(r"^- \*\*git_commit:\*\* `[^`]*`$", re.MULTILINE)
GIT_COMMIT_HTML = re.compile(
    r'(<span class="kv-label">git_commit</span><span class="kv-value"><code>)[^<]*(</code>)'
)
COMMIT_DEPENDENT = {"report_md", "report_html"}


def _normalized(markdown: str) -> str:
    return GIT_COMMIT_LINE.sub("- **git_commit:** `<commit>`", markdown)


def _normalized_artifact(report_dir: Path, name: str) -> str:
    text = (report_dir / name).read_text()
    if name == "report.md":
        return _normalized(text)
    if name == "report.html":
        return GIT_COMMIT_HTML.sub(r"\1<commit>\2", text)
    if name == "summary.json":
        summary = json.loads(text)
        for key in COMMIT_DEPENDENT & summary["artifact_hashes"].keys():
            text = text.replace(summary["artifact_hashes"][key], f"<{key}>")
    return text


def test_committed_reports__every_report_has_a_regeneration_command(repo_root: Path) -> None:
    committed = {path.parent.name for path in (repo_root / "reports").glob("*/report.md")}
    assert committed == set(REPORT_COMMANDS), (
        "Add each reports/<id>/report.md to REPORT_COMMANDS in this file, or delete the report."
    )


@pytest.mark.parametrize("report_id", sorted(REPORT_COMMANDS))
def test_committed_reports__match_fresh_render(
    report_id: str, repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo_root)
    args = REPORT_COMMANDS[report_id].split()
    result = CliRunner().invoke(app, [*args, "--out-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    fresh_dir = tmp_path / report_id
    committed_dir = repo_root / "reports" / report_id
    committed_names = sorted(path.name for path in committed_dir.iterdir() if path.is_file())
    fresh_names = sorted(path.name for path in fresh_dir.iterdir())
    assert committed_names == fresh_names, (
        f"reports/{report_id}/ holds {committed_names}, but a fresh render writes {fresh_names}."
    )
    summary = json.loads((committed_dir / "summary.json").read_text())
    for key, path in summary["artifact_paths"].items():
        digest = hashlib.sha256((committed_dir / path).read_bytes()).hexdigest()
        assert summary["artifact_hashes"][key] == digest, (
            f"reports/{report_id}/summary.json records a stale hash for {path}."
        )
    for name in committed_names:
        assert _normalized_artifact(fresh_dir, name) == _normalized_artifact(committed_dir, name), (
            f"reports/{report_id}/{name} is stale. Review the change, then regenerate it with:\n"
            f"  uv run --locked eval-audit {REPORT_COMMANDS[report_id]}"
        )


def test_humaneval_direct_completion_runs_parquet__cost_provenance_is_partial(
    repo_root: Path,
) -> None:
    """The Anthropic Messages API exposes no provider-side run total, so cost cannot reconcile.

    See the scouting/humaneval-direct-completion/normalize.py module docstring.
    """
    runs = pl.read_parquet(repo_root / "examples" / "humaneval-direct-completion" / "runs.parquet")
    assert sorted(runs["cost_provenance"].unique().to_list()) == ["partial"]
