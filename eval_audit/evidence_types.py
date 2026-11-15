"""Leaf types shared by evidence checks, errors, scouting paths, and reports."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

JsonScalar = str | int | float | bool | None
Json = JsonScalar | list["Json"] | dict[str, "Json"]
CheckSeverity = Literal["error", "warning", "info"]
CheckStatus = Literal["pass", "fail"]


@dataclass(frozen=True)
class EvidenceCheck:
    id: str
    severity: CheckSeverity
    status: CheckStatus
    message: str
    details: dict[str, Json]


@dataclass(frozen=True)
class EvidenceSource:
    fixture_path: Path
    fixture_sha256: str
    source_kind: Literal["canonical", "adapter"]
    source_dir: Path | None = None

    def display_path(self, repo_root: Path) -> str:
        try:
            return str(self.fixture_path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            return str(self.fixture_path.resolve())

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        source_kind: Literal["canonical", "adapter"],
        source_dir: Path | None = None,
    ) -> EvidenceSource:
        return cls(path, hashlib.sha256(path.read_bytes()).hexdigest(), source_kind, source_dir)
