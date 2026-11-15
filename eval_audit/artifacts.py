"""Contained publication of audit artifacts, with a completion marker and rollback."""

from __future__ import annotations

import sys
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO

from eval_audit.schema.artifacts import ARTIFACT_NAMES, STAGING_PREFIX

INCOMPLETE_MARKER = ".incomplete"


class ArtifactError(ValueError):
    """An artifact cannot be published or safely resolved."""


def audit_directory(root: Path, study_id: str) -> Path:
    if not study_id or study_id in {".", ".."} or "/" in study_id or "\\" in study_id:
        raise ArtifactError(f"study.id must be a single directory name, got {study_id!r}")
    if study_id.startswith(STAGING_PREFIX):
        raise ArtifactError(
            f"study.id must not start with reserved staging prefix {STAGING_PREFIX!r}"
        )
    destination = root / study_id
    if destination.resolve().parent != root.resolve():
        raise ArtifactError(f"audit destination escapes output root: {destination}")
    return destination


def artifact_path(directory: Path, name: str) -> Path:
    if name not in ARTIFACT_NAMES:
        raise ArtifactError(f"unsupported audit artifact name: {name!r}")
    path = directory / name
    if path.is_symlink() or path.resolve().parent != directory.resolve():
        raise ArtifactError(f"artifact must be a regular file inside {directory}: {name}")
    if path.exists() and not path.is_file():
        raise ArtifactError(f"artifact destination is not a file: {path}")
    return path


def _lock_file(lock: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(lock: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(lock, fcntl.LOCK_UN)


@contextmanager
def _publication_lock(directory: Path) -> Generator[None]:
    lock_path = directory.parent / f".{directory.name}.publish.lock"
    if lock_path.is_symlink():
        raise ArtifactError(f"publication lock must not be a symlink: {lock_path}")
    with lock_path.open("a+b") as lock:
        try:
            _lock_file(lock)
        except OSError as exc:
            raise ArtifactError(
                f"another writer is publishing {directory}; retry after it finishes"
            ) from exc
        try:
            yield
        finally:
            _unlock_file(lock)


def publish_artifacts(directory: Path, artifacts: Mapping[str, bytes], *, complete: bool) -> None:
    """Publish prepared bytes, writing summary last. Readers reject interrupted writes.

    A failed write restores the previous owned files. A process crash leaves the
    incomplete marker, so a reader cannot mistake mixed generations for a result.
    Re-running the audit replaces the complete owned set and clears that marker.
    """
    if complete and "summary.json" not in artifacts:
        raise ArtifactError("a completed audit requires summary.json")
    directory.mkdir(parents=True, exist_ok=True)
    with _publication_lock(directory):
        paths = {name: artifact_path(directory, name) for name in ARTIFACT_NAMES}
        marker = directory / INCOMPLETE_MARKER
        if marker.is_symlink():
            raise ArtifactError(f"completion marker must not be a symlink: {marker}")
        original_marker = marker.read_bytes() if marker.exists() else None
        previous = {name: path.read_bytes() for name, path in paths.items() if path.exists()}
        for name in artifacts:
            artifact_path(directory, name)
        with TemporaryDirectory(prefix=STAGING_PREFIX, dir=directory.parent) as staging:
            stage = Path(staging)
            for name, content in artifacts.items():
                (stage / name).write_bytes(content)
            marker.write_text(
                "Audit publication is incomplete. Re-run the audit to replace this generation.\n"
            )
            try:
                for name in sorted(artifacts, key=lambda name: name == "summary.json"):
                    (stage / name).replace(paths[name])
                obsolete = (
                    ARTIFACT_NAMES - artifacts.keys()
                    if complete
                    else {"summary.json", "report.html"}
                )
                for name in obsolete:
                    paths[name].unlink(missing_ok=True)
            except OSError:
                for name, path in paths.items():
                    if name in previous:
                        backup = stage / name
                        backup.write_bytes(previous[name])
                        backup.replace(path)
                    else:
                        path.unlink(missing_ok=True)
                if original_marker is None:
                    marker.unlink(missing_ok=True)
                else:
                    marker.write_bytes(original_marker)
                raise
            marker.unlink()
