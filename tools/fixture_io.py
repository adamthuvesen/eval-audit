"""Read pinned source artifacts and promote validated fixture files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field


class SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded_at: str
    revisions: dict[str, str]
    sources: dict[str, str] = Field(default_factory=dict)


def immutable_revision(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("revision must be a full 40-character lowercase commit SHA")
    return value


class FixtureSources:
    """Replay cached bytes offline, or fetch explicitly pinned refresh sources."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        mode: Literal["replay", "refresh"],
        revisions: dict[str, str],
    ) -> None:
        self.cache_dir = cache_dir
        self.mode = mode
        self.manifest_path = cache_dir / "manifest.json"
        if mode == "replay":
            if not self.manifest_path.is_file():
                raise ValueError(
                    f"missing replay manifest: {self.manifest_path}. "
                    "Create a refresh cache with explicit immutable revisions first."
                )
            self.manifest = SourceManifest.model_validate_json(self.manifest_path.read_bytes())
            for revision in self.manifest.revisions.values():
                immutable_revision(revision)
            if revisions and revisions != self.manifest.revisions:
                raise ValueError("replay revisions differ from the cached manifest")
        else:
            if not revisions:
                raise ValueError("refresh requires explicit immutable revisions")
            for revision in revisions.values():
                immutable_revision(revision)
            self.manifest = SourceManifest(
                recorded_at=datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                revisions=revisions,
            )

    def read(self, url: str) -> bytes:
        if self.mode == "replay":
            digest = self.manifest.sources.get(url)
            if digest is None or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"source missing from replay manifest: {url}")
            path = self.cache_dir / digest
            if not path.is_file():
                raise ValueError(f"missing replay source: {path}")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"replay source hash mismatch: {url}")
            return data
        if not url.startswith("https://") or not any(
            f"/{revision}/" in url for revision in self.manifest.revisions.values()
        ):
            raise ValueError(f"refresh source must use an immutable revision: {url}")
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
        except (OSError, urllib.error.URLError) as exc:
            raise ValueError(f"could not fetch {url}: {exc}") from exc
        digest = hashlib.sha256(data).hexdigest()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / digest
        if not path.exists():
            path.write_bytes(data)
        self.manifest.sources[url] = digest
        return data

    def save_manifest(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.manifest_path.with_suffix(".tmp")
        path.write_text(self.manifest.model_dump_json(indent=2) + "\n")
        path.replace(self.manifest_path)


def promote_fixture(
    frame: pl.DataFrame,
    provenance: Mapping[str, object],
    destination: Path,
    validate: Callable[[Path], object],
    *,
    accept_evidence_change: bool = False,
) -> None:
    """Validate a staged pair before replacement, and restore files on promotion errors.

    Pair replacement is not crash-atomic. Do not run concurrent writers or readers during promotion.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    names = ("runs.parquet", "provenance.json")
    with tempfile.TemporaryDirectory(prefix=".fixture-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        frame.write_parquet(stage / names[0])
        (stage / names[1]).write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
        validate(stage)
        originals = {
            name: (destination / name).read_bytes() if (destination / name).exists() else None
            for name in names
        }
        if not accept_evidence_change and any(
            original is not None and original != (stage / name).read_bytes()
            for name, original in originals.items()
        ):
            raise ValueError(
                "staged fixture differs from existing evidence. Use a new --output-dir, "
                "or --accept-evidence-change and review affected reports."
            )
        destination.mkdir(parents=True, exist_ok=True)
        promoted: list[str] = []
        try:
            for name in names:
                (stage / name).replace(destination / name)
                promoted.append(name)
        except OSError:
            for name in reversed(promoted):
                original = originals[name]
                if original is None:
                    (destination / name).unlink()
                else:
                    (destination / name).write_bytes(original)
            raise


def regeneration_parser(description: str, fixture_dir: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--mode", choices=("replay", "refresh"), default="replay")
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument(
        "--revision", type=immutable_revision, help="Hugging Face dataset commit SHA"
    )
    parser.add_argument("--output-dir", type=Path, default=fixture_dir)
    parser.add_argument(
        "--accept-evidence-change",
        action="store_true",
        help="Allow differing output to replace existing evidence. Review and rerun affected reports afterwards.",
    )
    return parser


def check_refresh_destination(mode: str, destination: Path, accept_evidence_change: bool) -> None:
    if mode == "refresh" and (destination / "runs.parquet").exists() and not accept_evidence_change:
        raise ValueError(
            "refresh would replace existing evidence. Use a new --output-dir, "
            "or --accept-evidence-change and review affected reports."
        )
