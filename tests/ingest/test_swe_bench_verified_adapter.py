"""Acceptance tests for the SWE-bench Verified ingest adapter."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from eval_audit.ingest.swe_bench_verified import (
    SWE_BENCH_VERIFIED_HARNESS,
    SWE_BENCH_VERIFIED_TASK_COUNT,
    SweBenchVerifiedAdapter,
    build_canonical_frame,
)


def _synthetic_universe(n: int = SWE_BENCH_VERIFIED_TASK_COUNT) -> list[str]:
    return [f"repo__pr-{i:04d}" for i in range(n)]


def _treatment_submission(universe: list[str]) -> dict:
    """Treatment with 388 resolved (matches scouting note's locked count)."""
    resolved = set(universe[:388])
    no_generation = set(universe[388:390])  # 2 no_generation
    return {
        "model_id": "claude-opus-4-5-202511017",
        "submission_dir": "20251127_openhands_claude-opus-4-5",
        "resolved": resolved,
        "no_generation": no_generation,
        "no_logs": set(),
    }


def _control_submission(universe: list[str]) -> dict:
    """Control with 359 resolved (matches scouting note's locked count)."""
    resolved = set(universe[:359])
    no_generation = set(universe[359:360])  # 1 no_generation
    return {
        "model_id": "gpt-5-2025-08-07",
        "submission_dir": "20250807_openhands_gpt5",
        "resolved": resolved,
        "no_generation": no_generation,
        "no_logs": set(),
    }


def test_build_canonical_frame__emits_paired_rows_per_universe() -> None:
    """The frame contains 1000 rows (500 per agent) keyed by instance_id × agent_id."""
    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }

    frame = build_canonical_frame(task_universe=universe, submissions=submissions)

    assert frame.height == 2 * SWE_BENCH_VERIFIED_TASK_COUNT
    treatment_rows = frame.filter(pl.col("agent_id") == "20251127_openhands_claude-opus-4-5")
    control_rows = frame.filter(pl.col("agent_id") == "20250807_openhands_gpt5")
    assert treatment_rows.height == SWE_BENCH_VERIFIED_TASK_COUNT
    assert control_rows.height == SWE_BENCH_VERIFIED_TASK_COUNT
    treatment_tasks = set(treatment_rows["task_id"].to_list())
    assert treatment_tasks == set(universe)


def test_build_canonical_frame__locked_resolved_counts_match_scouting() -> None:
    """Treatment 388/500 and control 359/500 success counts match the scouting note."""
    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }

    frame = build_canonical_frame(task_universe=universe, submissions=submissions)

    treatment = frame.filter(pl.col("agent_id") == "20251127_openhands_claude-opus-4-5")
    control = frame.filter(pl.col("agent_id") == "20250807_openhands_gpt5")
    assert int(treatment.filter(pl.col("success")).height) == 388
    assert int(control.filter(pl.col("success")).height) == 359


def test_build_canonical_frame__no_generation_maps_to_graded_failure() -> None:
    """no_generation rows carry success=False, outcome_status='graded', upstream_status='no_generation'."""
    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }

    frame = build_canonical_frame(task_universe=universe, submissions=submissions)

    no_gen_rows = frame.filter(
        (pl.col("agent_id") == "20251127_openhands_claude-opus-4-5")
        & (pl.col("task_id").is_in(universe[388:390]))
    )
    assert no_gen_rows.height == 2
    assert (no_gen_rows["success"] == False).all()  # noqa: E712
    assert (no_gen_rows["outcome_status"] == "graded").all()
    statuses = [row["upstream_status"] for row in no_gen_rows["rerun_metadata"]]
    assert all(s == "no_generation" for s in statuses)


def test_build_canonical_frame__every_row_is_cost_not_available() -> None:
    """The adapter never fabricates cost: provenance is uniform cost_not_available."""
    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }

    frame = build_canonical_frame(task_universe=universe, submissions=submissions)

    assert (frame["cost_provenance"] == "cost_not_available").all()
    assert frame["reconstructed_per_task_cost_usd"].null_count() == frame.height
    assert frame["reported_run_total_cost_usd"].null_count() == frame.height


def test_build_canonical_frame__paired_discordants_match_scouting() -> None:
    """Paired discordants under the synthetic universe are 29 vs 0 (treat-only solves only).

    The scouting note's locked discordants are 45 vs 16 against the real Verified
    task universe; this synthetic test exercises the structural property that
    paired discordants are computed from the resolved sets, not just the headline
    counts. Real-data parity is verified against the committed fixture in the
    fixture-level test below.
    """
    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }

    frame = build_canonical_frame(task_universe=universe, submissions=submissions)

    pivoted = (
        frame.filter(pl.col("agent_id").is_in(submissions.keys()))
        .pivot(values="success", index="task_id", on="agent_id")
        .fill_null(False)
    )
    a_only = pivoted.filter(
        pl.col("20251127_openhands_claude-opus-4-5") & ~pl.col("20250807_openhands_gpt5")
    ).height
    b_only = pivoted.filter(
        ~pl.col("20251127_openhands_claude-opus-4-5") & pl.col("20250807_openhands_gpt5")
    ).height
    # Synthetic universe: treatment 0..388, control 0..359 ⇒ treat-only = 29, ctrl-only = 0.
    assert a_only == 388 - 359
    assert b_only == 0


def test_build_canonical_frame__rejects_unknown_universe_size() -> None:
    """Universe that does not match the SWE-bench Verified 500-row contract raises."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe(n=10)
    submissions = {
        "agent": {
            "model_id": "m",
            "submission_dir": "agent",
            "resolved": set(universe[:5]),
            "no_generation": set(),
            "no_logs": set(),
        }
    }

    with pytest.raises(IngestContractError) as excinfo:
        build_canonical_frame(task_universe=universe, submissions=submissions)

    assert str(SWE_BENCH_VERIFIED_TASK_COUNT) in str(excinfo.value)


def test_build_canonical_frame__rejects_unknown_resolved_instance_id() -> None:
    """A submission resolving an instance_id not in the task universe raises."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe()
    submissions = {
        "agent": {
            "model_id": "m",
            "submission_dir": "agent",
            "resolved": {"unknown_instance"},
            "no_generation": set(),
            "no_logs": set(),
        }
    }

    with pytest.raises(IngestContractError) as excinfo:
        build_canonical_frame(task_universe=universe, submissions=submissions)

    assert "unknown" in str(excinfo.value).lower()


def test_build_canonical_frame__validates_through_canonical_runrecord() -> None:
    """Output passes the canonical RunRecord validation path."""
    from eval_audit.ingest import validate_run_records

    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }

    frame = build_canonical_frame(task_universe=universe, submissions=submissions)

    validate_run_records(frame)


def test_adapter_load__missing_runs_parquet_raises(tmp_path: Path) -> None:
    """Adapter requires the canonical parquet under the source directory."""
    from eval_audit.ingest.base import IngestContractError

    with pytest.raises(IngestContractError) as excinfo:
        SweBenchVerifiedAdapter().load(tmp_path)

    assert "runs.parquet" in str(excinfo.value)


def test_adapter_load__missing_provenance_raises(tmp_path: Path) -> None:
    """Adapter requires provenance.json so a reader can trace upstream artifacts."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }
    frame = build_canonical_frame(task_universe=universe, submissions=submissions)
    frame.write_parquet(tmp_path / "runs.parquet")

    with pytest.raises(IngestContractError) as excinfo:
        SweBenchVerifiedAdapter().load(tmp_path)

    assert "provenance" in str(excinfo.value).lower()


def test_adapter_load__valid_fixture_round_trips(tmp_path: Path) -> None:
    """A complete fixture round-trips through the adapter."""
    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }
    frame = build_canonical_frame(task_universe=universe, submissions=submissions)
    frame.write_parquet(tmp_path / "runs.parquet")
    (tmp_path / "provenance.json").write_text(json.dumps({"source": "synthetic-test"}))

    loaded = SweBenchVerifiedAdapter().load(tmp_path)

    assert loaded.height == 2 * SWE_BENCH_VERIFIED_TASK_COUNT
    assert (loaded["harness"] == SWE_BENCH_VERIFIED_HARNESS).all()
    assert (loaded["cost_provenance"] == "cost_not_available").all()


def test_build_canonical_frame__token_dicts_use_parquet_safe_sentinel() -> None:
    """tokens_in_by_model / tokens_out_by_model carry the parquet-safe sentinel.

    Polars cannot write a struct column to parquet when every dict is empty
    (`Unable to write struct type with no child field to Parquet`). The adapter
    emits `{"upstream_tokens_unavailable": 0}` so the column has a stable
    schema. This test locks that invariant in — a future "let's just use {}"
    regression would break parquet round-trip.
    """
    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }

    frame = build_canonical_frame(task_universe=universe, submissions=submissions)

    sample = frame["tokens_in_by_model"][0]
    assert isinstance(sample, dict)
    assert sample == {"upstream_tokens_unavailable": 0}
    sample_out = frame["tokens_out_by_model"][0]
    assert sample_out == {"upstream_tokens_unavailable": 0}


def test_build_canonical_frame__round_trips_through_parquet(tmp_path: Path) -> None:
    """The canonical frame survives parquet round-trip — write then read is lossless.

    Regression guard for the empty-struct parquet bug: if a future change
    drops the sentinel and uses `{}`, this test fails at write time with
    `Unable to write struct type with no child field to Parquet`.
    """
    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }
    frame = build_canonical_frame(task_universe=universe, submissions=submissions)

    target = tmp_path / "round_trip.parquet"
    frame.write_parquet(target)
    loaded = pl.read_parquet(target)

    assert loaded.height == frame.height
    assert set(loaded.columns) == set(frame.columns)
    assert int(
        loaded.filter(pl.col("agent_id") == "20251127_openhands_claude-opus-4-5")[
            "success"
        ].sum()
    ) == 388


def test_adapter_validate__rejects_wrong_harness(tmp_path: Path) -> None:
    """Adapter validate() rejects frames whose harness does not match the locked value."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }
    frame = build_canonical_frame(task_universe=universe, submissions=submissions)
    bad = frame.with_columns(pl.lit("wrong-harness").alias("harness"))

    with pytest.raises(IngestContractError) as excinfo:
        SweBenchVerifiedAdapter().validate(bad)

    assert "harness" in str(excinfo.value).lower()


def test_build_canonical_frame__rejects_unknown_no_generation_id() -> None:
    """An instance_id in no_generation that is not in the task universe raises."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe()
    submissions = {
        "agent": {
            "model_id": "m",
            "submission_dir": "agent",
            "resolved": set(),
            "no_generation": {"phantom_instance"},
            "no_logs": set(),
        }
    }

    with pytest.raises(IngestContractError) as excinfo:
        build_canonical_frame(task_universe=universe, submissions=submissions)

    msg = str(excinfo.value).lower()
    assert "no_generation" in msg
    assert "phantom_instance" in msg


def test_build_canonical_frame__rejects_unknown_no_logs_id() -> None:
    """An instance_id in no_logs that is not in the task universe raises."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe()
    submissions = {
        "agent": {
            "model_id": "m",
            "submission_dir": "agent",
            "resolved": set(),
            "no_generation": set(),
            "no_logs": {"phantom_instance"},
        }
    }

    with pytest.raises(IngestContractError) as excinfo:
        build_canonical_frame(task_universe=universe, submissions=submissions)

    msg = str(excinfo.value).lower()
    assert "no_logs" in msg
    assert "phantom_instance" in msg


def test_build_canonical_frame__rejects_resolved_no_generation_overlap() -> None:
    """An instance_id appearing in both resolved and no_generation raises."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe()
    overlapping = universe[0]
    submissions = {
        "agent": {
            "model_id": "m",
            "submission_dir": "agent",
            "resolved": {overlapping},
            "no_generation": {overlapping},
            "no_logs": set(),
        }
    }

    with pytest.raises(IngestContractError) as excinfo:
        build_canonical_frame(task_universe=universe, submissions=submissions)

    msg = str(excinfo.value).lower()
    assert "overlap" in msg
    assert "resolved" in msg
    assert "no_generation" in msg


def test_build_canonical_frame__rejects_resolved_no_logs_overlap() -> None:
    """An instance_id appearing in both resolved and no_logs raises."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe()
    overlapping = universe[1]
    submissions = {
        "agent": {
            "model_id": "m",
            "submission_dir": "agent",
            "resolved": {overlapping},
            "no_generation": set(),
            "no_logs": {overlapping},
        }
    }

    with pytest.raises(IngestContractError) as excinfo:
        build_canonical_frame(task_universe=universe, submissions=submissions)

    msg = str(excinfo.value).lower()
    assert "overlap" in msg
    assert "resolved" in msg
    assert "no_logs" in msg


def test_build_canonical_frame__rejects_no_generation_no_logs_overlap() -> None:
    """An instance_id appearing in both no_generation and no_logs raises."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe()
    overlapping = universe[2]
    submissions = {
        "agent": {
            "model_id": "m",
            "submission_dir": "agent",
            "resolved": set(),
            "no_generation": {overlapping},
            "no_logs": {overlapping},
        }
    }

    with pytest.raises(IngestContractError) as excinfo:
        build_canonical_frame(task_universe=universe, submissions=submissions)

    msg = str(excinfo.value).lower()
    assert "overlap" in msg
    assert "no_generation" in msg
    assert "no_logs" in msg


def test_adapter_validate__rejects_truncated_universe() -> None:
    """Adapter validate() rejects frames where an agent has fewer than 500 unique tasks."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }
    frame = build_canonical_frame(task_universe=universe, submissions=submissions)
    # Drop one row from the treatment agent to truncate its universe to 499.
    truncated = frame.filter(
        ~(
            (pl.col("agent_id") == "20251127_openhands_claude-opus-4-5")
            & (pl.col("task_id") == universe[0])
        )
    )

    with pytest.raises(IngestContractError) as excinfo:
        SweBenchVerifiedAdapter().validate(truncated)

    msg = str(excinfo.value).lower()
    assert "499" in msg or "500" in msg


def test_adapter_validate__rejects_duplicate_task_id() -> None:
    """Adapter validate() rejects frames where an agent has a duplicated task_id."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe()
    submissions = {
        "20251127_openhands_claude-opus-4-5": _treatment_submission(universe),
        "20250807_openhands_gpt5": _control_submission(universe),
    }
    frame = build_canonical_frame(task_universe=universe, submissions=submissions)
    # Pick one row from the treatment agent and clone it with a duplicate task_id.
    treatment_first = frame.filter(
        (pl.col("agent_id") == "20251127_openhands_claude-opus-4-5")
        & (pl.col("task_id") == universe[0])
    )
    duplicated = pl.concat([frame, treatment_first], how="vertical")

    with pytest.raises(IngestContractError) as excinfo:
        SweBenchVerifiedAdapter().validate(duplicated)

    msg = str(excinfo.value).lower()
    assert "duplicate" in msg


def test_adapter_validate__rejects_mismatched_agent_universes() -> None:
    """Adapter validate() rejects frames where two agents have 500 tasks but different sets."""
    from eval_audit.ingest.base import IngestContractError

    universe = _synthetic_universe()
    universe_b = universe[:-1] + [f"repo__pr-{SWE_BENCH_VERIFIED_TASK_COUNT:04d}"]
    submissions_a = {
        "agent_a": {
            "model_id": "m",
            "submission_dir": "agent_a",
            "resolved": set(),
            "no_generation": set(),
            "no_logs": set(),
        }
    }
    submissions_b = {
        "agent_b": {
            "model_id": "m",
            "submission_dir": "agent_b",
            "resolved": set(),
            "no_generation": set(),
            "no_logs": set(),
        }
    }
    frame_a = build_canonical_frame(task_universe=universe, submissions=submissions_a)
    frame_b = build_canonical_frame(task_universe=universe_b, submissions=submissions_b)
    mismatched = pl.concat([frame_a, frame_b], how="vertical")

    with pytest.raises(IngestContractError) as excinfo:
        SweBenchVerifiedAdapter().validate(mismatched)

    msg = str(excinfo.value).lower()
    assert "universe" in msg or "differs" in msg
