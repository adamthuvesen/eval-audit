"""Round-trip test for examples/byo-minimal/make_runs.py.

Pins the invariant: re-running make_runs.py produces a parquet whose rows
are equal to the committed runs.parquet. Edits to either must come together.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import polars as pl

from eval_audit.ingest import load_run_records


def test_byo_minimal__committed_parquet_validates(repo_root: Path) -> None:
    """The committed example parquet itself loads cleanly."""
    frame = load_run_records(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    assert frame.height == 20


def test_byo_minimal__make_runs_round_trips(repo_root: Path, tmp_path: Path) -> None:
    """Running make_runs.py in a tmp dir produces row-equal output to the committed parquet."""
    src_dir = repo_root / "examples" / "byo-minimal"
    work_dir = tmp_path / "byo-minimal"
    work_dir.mkdir()
    shutil.copy(src_dir / "make_runs.py", work_dir / "make_runs.py")

    result = subprocess.run(
        [sys.executable, str(work_dir / "make_runs.py")],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"make_runs.py failed: {result.stderr}"

    produced = pl.read_parquet(work_dir / "runs.parquet")
    committed = pl.read_parquet(src_dir / "runs.parquet")

    assert produced.height == committed.height
    a = produced.sort(["agent_id", "task_id"])
    b = committed.sort(["agent_id", "task_id"])
    for col in sorted(a.columns):
        assert a[col].to_list() == b[col].to_list(), (
            f"column {col!r} drifts between regenerated and committed parquet; "
            f"either the script changed and the committed parquet wasn't updated, "
            f"or the parquet was hand-edited"
        )
