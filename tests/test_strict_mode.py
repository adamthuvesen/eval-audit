"""No file turns strict type checking or lint off, and every inline `noqa` gives a reason."""

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Any file-level comment except a bare `strict` can turn a mode or a single rule off.
DOWNGRADE = re.compile(r"^\s*#\s*(?:based)?pyright:(?!\s*strict\s*$)")


def is_python_file(path: Path) -> bool:
    if path.suffix:
        return path.suffix in {".py", ".pyi"}
    with path.open("rb") as handle:
        first_line = handle.readline()
    return first_line.startswith(b"#!") and b"python" in first_line


def git_env() -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}


def checkout_python_files(root: Path = ROOT) -> list[Path]:
    """Tracked files plus new files the agent has not staged yet."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        env=git_env(),
        capture_output=True,
        check=True,
    ).stdout.decode()
    paths = (root / name for name in listing.split("\0") if name)
    return [path for path in paths if path.is_file() and is_python_file(path)]


def downgrades_in(paths: list[Path], root: Path = ROOT) -> list[str]:
    return [
        f"{path.relative_to(root)}:{number}"
        for path in paths
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), start=1)
        if DOWNGRADE.match(line)
    ]


def test_scan_finds_an_unstaged_downgrade(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], env=git_env(), check=True)
    (tmp_path / "probe.py").write_text(
        "x: int = 1\n# pyright: basic\n# pyright: reportArgumentType=false\n# pyright: strict\n"
    )
    found = downgrades_in(checkout_python_files(tmp_path), tmp_path)
    assert found == ["probe.py:2", "probe.py:3"]


def test_no_file_downgrades_type_checking_mode() -> None:
    downgrades = downgrades_in(checkout_python_files())
    assert not downgrades, "file-level `# pyright:` comment turns strict mode off: " + ", ".join(
        downgrades
    )


FILE_WIDE_LINT_OFF = re.compile(r"^\s*#\s*(?:ruff|flake8):\s*noqa", re.IGNORECASE)
NOQA_WITHOUT_REASON = re.compile(
    r"#\s*noqa\b(?!(?::\s*[A-Z]+\d+(?:\s*,\s*[A-Z]+\d+)*)\s+-\s+\S)", re.IGNORECASE
)


def lint_suppression_problems(paths: list[Path], root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    for path in paths:
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
            where = f"{path.relative_to(root)}:{number}"
            if FILE_WIDE_LINT_OFF.match(line):
                problems.append(f"{where} turns lint off for the whole file")
            elif NOQA_WITHOUT_REASON.search(line) and path.name != Path(__file__).name:
                problems.append(f"{where} has a noqa with no rule code or no ` - reason`")
    return problems


def test_scan_finds_lint_suppressions_without_a_reason(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], env=git_env(), check=True)
    (tmp_path / "probe.py").write_text(
        "# ruff: noqa: F401, B006\n"
        "import os  # noqa\n"
        "import sys  # noqa: F401\n"
        "import re  # noqa: F401 - re-exported\n"
    )
    assert lint_suppression_problems(checkout_python_files(tmp_path), tmp_path) == [
        "probe.py:1 turns lint off for the whole file",
        "probe.py:2 has a noqa with no rule code or no ` - reason`",
        "probe.py:3 has a noqa with no rule code or no ` - reason`",
    ]


def test_lint_suppressions_are_scoped_and_explained() -> None:
    problems = lint_suppression_problems(checkout_python_files())
    assert not problems, "; ".join(problems)
