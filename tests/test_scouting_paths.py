"""Unit tests for the shared scouting-path resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval_audit.scouting_paths import DECISION_DOC_ALIAS, resolve_decision_doc


def test_alias_maps_gaia_to_historical_filename(tmp_path: Path) -> None:
    path, label = resolve_decision_doc(tmp_path, "gaia", "gaia-hal-generalist")
    assert label == "scouting/gaia-hal-generalist-decision.md"
    assert path == tmp_path / "scouting" / "gaia-hal-generalist-decision.md"


def test_alias_maps_tau_bench_to_hyphenated_filename(tmp_path: Path) -> None:
    path, label = resolve_decision_doc(
        tmp_path, "tau_bench", "tau-bench-airline-tool-calling"
    )
    assert label == "scouting/tau-bench-airline-tool-calling-decision.md"
    assert (
        path == tmp_path / "scouting" / "tau-bench-airline-tool-calling-decision.md"
    )


def test_falls_back_to_benchmark_keyed_path_when_present(tmp_path: Path) -> None:
    scouting = tmp_path / "scouting"
    scouting.mkdir()
    (scouting / "swe-bench-verified-decision.md").write_text("stub\n")

    path, label = resolve_decision_doc(
        tmp_path, "swe-bench-verified", "swe-bench-verified-openhands"
    )

    assert label == "scouting/swe-bench-verified-decision.md"
    assert path == scouting / "swe-bench-verified-decision.md"


def test_falls_back_to_study_id_when_benchmark_keyed_path_absent(
    tmp_path: Path,
) -> None:
    path, label = resolve_decision_doc(
        tmp_path, "humaneval", "humaneval-direct-completion"
    )
    assert label == "scouting/humaneval-direct-completion-decision.md"
    assert (
        path == tmp_path / "scouting" / "humaneval-direct-completion-decision.md"
    )


@pytest.mark.parametrize("benchmark", sorted(DECISION_DOC_ALIAS))
def test_alias_keys_all_resolve_to_scouting_paths(
    tmp_path: Path, benchmark: str
) -> None:
    path, label = resolve_decision_doc(tmp_path, benchmark, "ignored-study-id")
    assert label.startswith("scouting/")
    assert path == tmp_path / label
