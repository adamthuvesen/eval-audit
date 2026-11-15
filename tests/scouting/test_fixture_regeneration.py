"""Offline replay and promotion checks for public fixture maintenance."""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import polars as pl
import pytest

from tools import regenerate_swe_bench_verified as swe
from tools import regenerate_terminal_bench_mux as terminal
from tools.fixture_io import FixtureSources, SourceManifest, promote_fixture

REVISION = "a" * 40


def _cache(tmp_path: Path, artifacts: dict[str, bytes], revisions: dict[str, str]) -> Path:
    cache = tmp_path / "cache"
    cache.mkdir()
    manifest = SourceManifest(recorded_at="2026-01-01T00:00:00Z", revisions=revisions)
    for url, data in artifacts.items():
        digest = hashlib.sha256(data).hexdigest()
        (cache / digest).write_bytes(data)
        manifest.sources[url] = digest
    (cache / "manifest.json").write_text(manifest.model_dump_json())
    return cache


def _forbid_network(*_args: object, **_kwargs: object) -> None:
    pytest.fail("offline replay must not call the network")


def test_replay__checks_hash_and_never_calls_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"https://example.test/resolve/{REVISION}/data"
    cache = _cache(tmp_path, {url: b"source"}, {"dataset": REVISION})
    monkeypatch.setattr("urllib.request.urlopen", _forbid_network)
    sources = FixtureSources(cache, mode="replay", revisions={})
    assert sources.read(url) == b"source"
    digest = sources.manifest.sources[url]
    (cache / digest).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="hash mismatch"):
        sources.read(url)


def test_refresh__requires_immutable_url_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("urllib.request.urlopen", _forbid_network)
    sources = FixtureSources(tmp_path, mode="refresh", revisions={"dataset": REVISION})
    with pytest.raises(ValueError, match="immutable revision"):
        sources.read("https://example.test/resolve/main/data")


def test_promotion__validation_failure_preserves_both_files(tmp_path: Path) -> None:
    destination = tmp_path / "fixture"
    destination.mkdir()
    (destination / "runs.parquet").write_bytes(b"original-runs")
    (destination / "provenance.json").write_bytes(b"original-provenance")

    def reject(stage: Path) -> None:
        assert (stage / "runs.parquet").is_file()
        assert json.loads((stage / "provenance.json").read_text()) == {"new": True}
        raise ValueError("invalid staged fixture")

    with pytest.raises(ValueError, match="invalid staged fixture"):
        promote_fixture(pl.DataFrame({"value": [1]}), {"new": True}, destination, reject)
    assert (destination / "runs.parquet").read_bytes() == b"original-runs"
    assert (destination / "provenance.json").read_bytes() == b"original-provenance"


def test_promotion__second_replace_failure_restores_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "fixture"
    destination.mkdir()
    (destination / "runs.parquet").write_bytes(b"original-runs")
    (destination / "provenance.json").write_bytes(b"original-provenance")
    replace = Path.replace

    def fail_provenance(path: Path, target: Path) -> Path:
        if path.name == "provenance.json":
            raise OSError("simulated promotion failure")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_provenance)
    with pytest.raises(OSError, match="simulated promotion failure"):
        promote_fixture(
            pl.DataFrame({"value": [1]}),
            {},
            destination,
            lambda _stage: None,
            accept_evidence_change=True,
        )
    assert (destination / "runs.parquet").read_bytes() == b"original-runs"
    assert (destination / "provenance.json").read_bytes() == b"original-provenance"


@pytest.mark.parametrize("bad_status", [False, True])
def test_swe__offline_replay_stages_before_promotion(
    bad_status: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    universe = [f"task-{index}" for index in range(swe.SWE_BENCH_VERIFIED_TASK_COUNT)]
    parquet = io.BytesIO()
    pl.DataFrame({"instance_id": universe}).write_parquet(parquet)
    artifacts = {swe.VERIFIED_PARQUET_URL.format(revision=REVISION): parquet.getvalue()}
    for submission in (swe.TREATMENT_DIR, swe.CONTROL_DIR):
        url = swe.RESULTS_URL_TEMPLATE.format(commit=REVISION, submission=submission)
        artifacts[url] = json.dumps(
            {"resolved": ["unknown-task"] if bad_status else universe[:2]}
        ).encode()
    cache = _cache(tmp_path, artifacts, {"dataset": REVISION, "experiments": REVISION})
    destination = tmp_path / "fixture"
    destination.mkdir()
    (destination / "runs.parquet").write_bytes(b"original-runs")
    (destination / "provenance.json").write_bytes(b"original-provenance")
    monkeypatch.setattr("urllib.request.urlopen", _forbid_network)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "regenerate",
            "--cache-dir",
            str(cache),
            "--output-dir",
            str(destination),
            "--accept-evidence-change",
        ],
    )
    if bad_status:
        with pytest.raises(RuntimeError, match="contains unknown"):
            swe.main()
        assert (destination / "runs.parquet").read_bytes() == b"original-runs"
        assert (destination / "provenance.json").read_bytes() == b"original-provenance"
    else:
        swe.main()
        first = (destination / "runs.parquet").read_bytes()
        provenance = (destination / "provenance.json").read_bytes()
        assert pl.read_parquet(destination / "runs.parquet").height == 1000
        swe.main()
        assert (destination / "runs.parquet").read_bytes() == first
        assert (destination / "provenance.json").read_bytes() == provenance
        assert json.loads(provenance)["fetched_at_utc"] == "2026-01-01T00:00:00Z"


@pytest.mark.parametrize(
    "missing", ["n_input_tokens", "n_output_tokens", "started_at", "finished_at"]
)
def test_terminal__missing_usage_or_timestamp_rejected_offline(
    missing: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_result = {"n_input_tokens": 1, "n_output_tokens": 2}
    record: dict[str, object] = {
        "agent_result": agent_result,
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
    }
    if missing.startswith("n_"):
        agent_result.pop(missing)
    else:
        record.pop(missing)
    path = f"{terminal.SUBMISSION_ROOT}/submission/run/trial/result.json"
    url = f"{terminal.DATASET_ROOT_URL}/resolve/{REVISION}/{path}"
    cache = _cache(tmp_path, {url: json.dumps(record).encode()}, {"dataset": REVISION})
    monkeypatch.setattr("urllib.request.urlopen", _forbid_network)
    with pytest.raises(ValueError, match=missing):
        terminal._result(
            FixtureSources(cache, mode="replay", revisions={}), "submission", "run", "trial"
        )


def test_terminal__offline_replay_builds_and_validates_full_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from urllib.parse import quote

    artifacts: dict[str, bytes] = {}
    for submission in terminal.SUBMISSIONS:
        base = f"{terminal.SUBMISSION_ROOT}/{submission}"
        artifacts[f"{terminal.DATASET_ROOT_URL}/resolve/{REVISION}/{base}/metadata.yaml"] = (
            b'{"model": {"name": "test-model"}}'
        )
        runs = [f"run-{index}" for index in range(5)]
        tree_url = f"https://huggingface.co/api/datasets/{terminal.DATASET_ID}/tree/{REVISION}"
        artifacts[f"{tree_url}/{quote(base, safe='/')}?limit=1000"] = json.dumps(
            [{"path": f"{base}/{run_id}", "type": "directory"} for run_id in runs]
        ).encode()
        for run_id in runs:
            trials = [f"task-{index}" for index in range(terminal.TERMINAL_BENCH_2_TASK_COUNT)]
            artifacts[f"{tree_url}/{quote(base, safe='/')}/{run_id}?limit=1000"] = json.dumps(
                [{"path": f"{base}/{run_id}/{trial}", "type": "directory"} for trial in trials]
            ).encode()
            for trial in trials:
                url = f"{terminal.DATASET_ROOT_URL}/resolve/{REVISION}/{base}/{run_id}/{trial}/result.json"
                artifacts[url] = json.dumps(
                    {
                        "task_name": trial,
                        "agent_result": {"n_input_tokens": 1, "n_output_tokens": 2},
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "2026-01-01T00:00:01Z",
                        "verifier_result": {"rewards": {"reward": 1.0}},
                    }
                ).encode()
    cache = _cache(tmp_path, artifacts, {"dataset": REVISION})
    destination = tmp_path / "fixture"
    monkeypatch.setattr("urllib.request.urlopen", _forbid_network)
    monkeypatch.setattr(
        sys, "argv", ["regenerate", "--cache-dir", str(cache), "--output-dir", str(destination)]
    )
    terminal.main()
    frame = pl.read_parquet(destination / "runs.parquet")
    assert frame.height == 2 * 5 * terminal.TERMINAL_BENCH_2_TASK_COUNT
    assert frame["success"].all()
    assert frame["reconstructed_per_task_cost_usd"].null_count() == frame.height
    assert json.loads((destination / "provenance.json").read_text())["dataset_revision"] == REVISION


def test_promotion__requires_explicit_acceptance_for_different_evidence(tmp_path: Path) -> None:
    destination = tmp_path / "fixture"
    destination.mkdir()
    (destination / "runs.parquet").write_bytes(b"recorded-evidence")
    with pytest.raises(ValueError, match="differs from existing evidence"):
        promote_fixture(pl.DataFrame({"value": [1]}), {}, destination, lambda _stage: None)
    assert (destination / "runs.parquet").read_bytes() == b"recorded-evidence"
