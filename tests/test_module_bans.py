"""Process, network, and paid-SDK modules stay banned outside their named owner files."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROBE = """import asyncio
import os
import subprocess
from urllib import request

subprocess.run(["true"], check=True)
os.system("true")
request.urlopen("x")
asyncio.run(asyncio.create_subprocess_exec("true"))
"""


def test_module_bans__fire_in_a_new_package_module(repo_root: Path) -> None:
    ruff = Path(sys.executable).parent / "ruff"
    done = subprocess.run(
        [str(ruff), "check", "--no-cache", "--stdin-filename", "eval_audit/new_module.py", "-"],
        cwd=repo_root,
        input=PROBE,
        capture_output=True,
        text=True,
        check=False,
    )
    banned = sorted(
        line.split("`")[1] for line in done.stdout.splitlines() if line.startswith("TID251")
    )
    assert banned == ["asyncio", "os.system", "subprocess", "urllib.request"], done.stdout
