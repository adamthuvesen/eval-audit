"""No file turns strict type checking or lint off, and every inline `noqa` gives a reason."""

import ast
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
    assert not downgrades, (
        "file-level `# pyright:` comment turns strict mode off: "
        + ", ".join(downgrades)
        + ". Remove it; fix the type error, or put `# pyright: ignore[rule]  # reason` on the line."
    )


FILE_WIDE_LINT_OFF = re.compile(r"^\s*#\s*(?:ruff|flake8):\s*noqa", re.IGNORECASE)
NOQA_WITHOUT_REASON = re.compile(
    r"#\s*noqa\b(?!(?::\s*[A-Z]+\d+(?:\s*,\s*[A-Z]+\d+)*)\s+-\s+\S)", re.IGNORECASE
)
NOQA_ON_BAN = re.compile(r"#\s*noqa\b[^#\n]*\bTID251\b", re.IGNORECASE)


def lint_suppression_problems(paths: list[Path], root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    for path in paths:
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
            where = f"{path.relative_to(root)}:{number}"
            if FILE_WIDE_LINT_OFF.match(line):
                problems.append(
                    f"{where} turns lint off for the whole file; remove it and use `# noqa: CODE - reason` on the line"
                )
            elif path.name == Path(__file__).name:
                continue
            elif NOQA_ON_BAN.search(line):
                problems.append(
                    f"{where} silences a banned API; move the call to an owner file, or add a TID251 per-file-ignore in pyproject.toml"
                )
            elif NOQA_WITHOUT_REASON.search(line):
                problems.append(
                    f"{where} has a noqa with no rule code or no reason; write `# noqa: CODE - reason`"
                )
    return problems


def test_scan_finds_lint_suppressions_without_a_reason(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], env=git_env(), check=True)
    (tmp_path / "probe.py").write_text(
        "# ruff: noqa: F401, B006\n"
        "import os  # noqa\n"
        "import sys  # noqa: F401\n"
        "import re  # noqa: F401 - re-exported\n"
        "import subprocess  # noqa: TID251 - needed here\n"
    )
    assert lint_suppression_problems(checkout_python_files(tmp_path), tmp_path) == [
        "probe.py:1 turns lint off for the whole file; remove it and use `# noqa: CODE - reason` on the line",
        "probe.py:2 has a noqa with no rule code or no reason; write `# noqa: CODE - reason`",
        "probe.py:3 has a noqa with no rule code or no reason; write `# noqa: CODE - reason`",
        "probe.py:5 silences a banned API; move the call to an owner file, or add a TID251 per-file-ignore in pyproject.toml",
    ]


def test_lint_suppressions_are_scoped_and_explained() -> None:
    problems = lint_suppression_problems(checkout_python_files())
    assert not problems, "; ".join(problems)


PYRIGHT_IGNORE = re.compile(r"#\s*pyright:\s*ignore")
IGNORE_WITH_RULE_AND_REASON = re.compile(
    r"#\s*pyright:\s*ignore\[[A-Za-z]+(?:,\s*[A-Za-z]+)*\]\s+#\s*\S"
)


def unexplained_pyright_ignores(paths: list[Path], root: Path = ROOT) -> list[str]:
    return [
        f"{path.relative_to(root)}:{number}"
        for path in paths
        if path.name != Path(__file__).name
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), start=1)
        if PYRIGHT_IGNORE.search(line) and not IGNORE_WITH_RULE_AND_REASON.search(line)
    ]


def test_scan_finds_pyright_ignores_without_a_reason(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], env=git_env(), check=True)
    (tmp_path / "probe.py").write_text(
        "a = 1  # pyright: ignore[reportAny]\n"
        "b = 1  # pyright: ignore[reportAny]  # runtime proof\n"
        "c = 1  # pyright: ignore\n"
    )
    assert unexplained_pyright_ignores(checkout_python_files(tmp_path), tmp_path) == [
        "probe.py:1",
        "probe.py:3",
    ]


def test_pyright_ignores_name_a_rule_and_give_a_reason() -> None:
    problems = unexplained_pyright_ignores(checkout_python_files())
    assert not problems, "write `# pyright: ignore[rule]  # reason`: " + ", ".join(problems)


# pytest reads a mark's reason only from its keyword; pytest.skip and unittest.skip take it first.
SKIP_MARKERS = frozenset({"pytest.skip", "unittest.skip", "pytest.mark.skip", "pytest.mark.xfail"})


def dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


def has_skip_reason(call: ast.Call, marker: str) -> bool:
    keyword = next((item.value for item in call.keywords if item.arg == "reason"), None)
    if marker.startswith("pytest.mark."):
        reason = keyword
    else:
        reason = call.args[0] if call.args else keyword
    return (
        isinstance(reason, ast.Constant)
        and isinstance(reason.value, str)
        and bool(reason.value.strip())
    )


def skips_without_a_reason(paths: list[Path], root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(errors="replace"), filename=str(path))
        called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                marker = dotted_name(node.func)
                if (
                    marker is not None
                    and marker in SKIP_MARKERS
                    and not has_skip_reason(node, marker)
                ):
                    problems.append(f"{path.relative_to(root)}:{node.lineno}")
            elif isinstance(node, ast.Name | ast.Attribute):
                bare = id(node) not in called and dotted_name(node) in SKIP_MARKERS
                if bare:
                    problems.append(f"{path.relative_to(root)}:{node.lineno}")
    return problems


def test_scan_finds_skips_and_xfails_without_a_reason(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], env=git_env(), check=True)
    (tmp_path / "probe.py").write_text(
        "import pytest\n"
        "import unittest\n"
        "@pytest.mark.skip\n"
        "def test_bare() -> None: ...\n"
        "@pytest.mark.skip(reason='')\n"
        "def test_empty() -> None: ...\n"
        "@pytest.mark.xfail(strict=True)\n"
        "def test_keyword_missing() -> None: ...\n"
        "@pytest.mark.skip(reason='waits for the fixture')\n"
        "def test_ok() -> None: ...\n"
        "def test_skip_call() -> None:\n"
        "    pytest.skip()\n"
        "    pytest.skip('needs network')\n"
        "@unittest.skip('needs a TTY')\n"
        "def test_unittest_ok() -> None: ...\n"
    )
    assert skips_without_a_reason(checkout_python_files(tmp_path), tmp_path) == [
        "probe.py:3",
        "probe.py:5",
        "probe.py:7",
        "probe.py:12",
    ]


def test_skips_and_xfails_give_a_reason() -> None:
    problems = skips_without_a_reason(checkout_python_files())
    assert not problems, (
        "give every skip and xfail a reason: "
        + ", ".join(problems)
        + ". Pass reason='...' to pytest.mark.skip or xfail; pass the reason first to pytest.skip()."
    )
