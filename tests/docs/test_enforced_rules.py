"""Every `Enforced by` citation in AGENTS.md names a real file and, after `::`, a name it defines."""

from __future__ import annotations

import re
from pathlib import Path

# A name is defined by a Python def/class, a Make target, a TOML table, or a TOML/YAML key.
DEFINITION = r"^\s*(?:(?:async\s+)?def\s+{0}\(|class\s+{0}\b|{0}\s*:|\[+{0}\]+\s*$|{0}\s*=)"


def _rows(agents_md: str) -> list[str]:
    assert "\n## Enforced Rules\n" in agents_md, "AGENTS.md must keep a `## Enforced Rules` section"
    section = agents_md.split("\n## Enforced Rules\n", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("|")][2:]
    assert rows, "AGENTS.md `## Enforced Rules` table has no rows"
    return rows


def citation_problems(agents_md: str, repo_root: Path) -> list[str]:
    problems: list[str] = []
    for row in _rows(agents_md):
        citations = re.findall(r"`([^`]+)`", row.split("|")[2])
        if not citations:
            problems.append(f"row cites nothing: {row}")
        for citation in citations:
            path, _, name = citation.partition("::")
            target = repo_root / path
            if not target.is_file():
                problems.append(f"{citation}: file {path} does not exist")
            elif not name:
                problems.append(f"{citation}: cite an exact name as {path}::<name>")
            elif not re.search(
                DEFINITION.format(re.escape(name)), target.read_text(), re.MULTILINE
            ):
                problems.append(f"{citation}: {path} does not define {name!r}")
    return problems


def test_enforced_rules__flags_rotted_citations(repo_root: Path) -> None:
    table = (
        "\n## Enforced Rules\n\n| Rule | Enforced by |\n| --- | --- |\n"
        "| a | `Makefile::check-typo` |\n| b | `missing.py` |\n| c | none |\n"
        "| d | `Makefile` |\n"
    )
    assert citation_problems(table, repo_root) == [
        "Makefile::check-typo: Makefile does not define 'check-typo'",
        "missing.py: file missing.py does not exist",
        "row cites nothing: | c | none |",
        "Makefile: cite an exact name as Makefile::<name>",
    ]


def test_enforced_rules__citations_exist(repo_root: Path) -> None:
    problems = citation_problems((repo_root / "AGENTS.md").read_text(), repo_root)
    assert not problems, (
        "AGENTS.md `## Enforced Rules` cites missing enforcement. Fix the citation "
        "or restore the check:\n" + "\n".join(problems)
    )
