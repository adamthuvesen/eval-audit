"""Every `Enforced by` citation in AGENTS.md names a real file and, after `::`, text in it."""

from __future__ import annotations

import re
from pathlib import Path


def _citations(agents_md: str) -> list[str]:
    section = agents_md.split("## Enforced Rules", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("|")][2:]
    assert rows, "AGENTS.md `## Enforced Rules` table has no rows"
    return [ref for row in rows for ref in re.findall(r"`([^`]+)`", row.split("|")[2])]


def test_enforced_rules__citations_exist(repo_root: Path) -> None:
    citations = _citations((repo_root / "AGENTS.md").read_text())
    missing = []
    for citation in citations:
        path, _, needle = citation.partition("::")
        target = repo_root / path
        if not target.is_file():
            missing.append(f"{citation}: file {path} does not exist")
        elif needle and needle not in target.read_text():
            missing.append(f"{citation}: {needle!r} not found in {path}")
    assert not missing, (
        "AGENTS.md `## Enforced Rules` cites missing enforcement. Fix the citation "
        "or restore the check:\n" + "\n".join(missing)
    )
