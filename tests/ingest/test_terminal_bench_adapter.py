"""Acceptance tests for the Terminal-Bench 2.0 Mux ingest adapter."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from eval_audit.ingest.terminal_bench import (
    TERMINAL_BENCH_2_HARNESS,
    TERMINAL_BENCH_2_RUNS_PER_AGENT,
    TERMINAL_BENCH_2_TASK_COUNT,
    TerminalBenchMuxAdapter,
    build_canonical_frame,
)


def _metadata(model_name: str, display_name: str) -> dict:
    return {
        "agent": {"display_name": "Mux"},
        "model": {
            "name": model_name,
            "display_name": display_name,
            "provider": model_name.split("/", maxsplit=1)[0],
        },
    }


def _record(task_num: int, model_name: str, reward: float = 1.0) -> dict:
    task_name = f"terminal-task-{task_num:03d}"
    return {
        "task_name": task_name,
        "trial_name": f"{task_name}__trial",
        "source": "terminal-bench",
        "started_at": "2026-02-11T13:05:34.066638Z",
        "finished_at": "2026-02-11T13:06:34.066638Z",
        "task_id": {
            "git_url": "https://github.com/example/tasks.git",
            "git_commit_id": "abc123",
        },
        "config": {
            "agent": {
                "import_path": "benchmarks.terminal_bench.mux_agent:MuxAgent",
                "model_name": model_name,
            }
        },
        "agent_result": {
            "n_input_tokens": 100 + task_num,
            "n_output_tokens": 10 + task_num,
            "cost_usd": None,
        },
        "verifier_result": {"rewards": {"reward": reward}},
        "_submission_path": f"submissions/{task_name}/result.json",
    }


def _submission(model_name: str, display_name: str) -> dict:
    return {
        "metadata": _metadata(model_name, display_name),
        "runs": {
            f"2026-02-11__run-{run_num:02d}": [
                _record(task_num, model_name, reward=float(task_num % 2 == 0))
                for task_num in range(TERMINAL_BENCH_2_TASK_COUNT)
            ]
            for run_num in range(TERMINAL_BENCH_2_RUNS_PER_AGENT)
        },
    }


def test_build_canonical_frame__emits_expected_public_submission_shape() -> None:
    submissions = {
        "Mux__GPT-5.3-Codex": _submission("openai/gpt-5.3-codex", "GPT-5.3 Codex"),
        "Mux__Claude-Opus-4.6": _submission(
            "anthropic/claude-opus-4-6", "Claude Opus 4.6"
        ),
    }

    frame = build_canonical_frame(submissions=submissions)

    expected_rows = (
        2 * TERMINAL_BENCH_2_RUNS_PER_AGENT * TERMINAL_BENCH_2_TASK_COUNT
    )
    assert frame.height == expected_rows
    assert sorted(frame["agent_id"].unique().to_list()) == sorted(submissions)
    assert (frame["harness"] == TERMINAL_BENCH_2_HARNESS).all()


def test_build_canonical_frame__every_row_is_cost_not_available() -> None:
    submissions = {
        "Mux__GPT-5.3-Codex": _submission("openai/gpt-5.3-codex", "GPT-5.3 Codex"),
        "Mux__Claude-Opus-4.6": _submission(
            "anthropic/claude-opus-4-6", "Claude Opus 4.6"
        ),
    }

    frame = build_canonical_frame(submissions=submissions)

    assert (frame["cost_provenance"] == "cost_not_available").all()
    assert frame["reconstructed_per_task_cost_usd"].null_count() == frame.height
    assert frame["reported_run_total_cost_usd"].null_count() == frame.height


def test_build_canonical_frame__suppresses_incomplete_upstream_cost() -> None:
    submissions = {
        "Mux__GPT-5.3-Codex": _submission("openai/gpt-5.3-codex", "GPT-5.3 Codex"),
        "Mux__Claude-Opus-4.6": _submission(
            "anthropic/claude-opus-4-6", "Claude Opus 4.6"
        ),
    }
    first_run = submissions["Mux__GPT-5.3-Codex"]["runs"]["2026-02-11__run-00"]
    first_run[0]["agent_result"]["cost_usd"] = 0.01

    frame = build_canonical_frame(submissions=submissions)

    row = frame.filter(
        (pl.col("agent_id") == "Mux__GPT-5.3-Codex")
        & (pl.col("task_id") == "terminal-task-000")
    ).row(0, named=True)
    assert row["cost_provenance"] == "cost_not_available"
    assert row["reconstructed_per_task_cost_usd"] is None
    assert row["rerun_metadata"]["upstream_cost_usd"] == "0.01"


def test_build_canonical_frame__validates_through_canonical_runrecord() -> None:
    from eval_audit.ingest import validate_run_records

    submissions = {
        "Mux__GPT-5.3-Codex": _submission("openai/gpt-5.3-codex", "GPT-5.3 Codex"),
        "Mux__Claude-Opus-4.6": _submission(
            "anthropic/claude-opus-4-6", "Claude Opus 4.6"
        ),
    }

    frame = build_canonical_frame(submissions=submissions)

    validate_run_records(frame)


def test_adapter_load__missing_runs_parquet_raises(tmp_path: Path) -> None:
    from eval_audit.ingest.base import IngestContractError

    with pytest.raises(IngestContractError) as excinfo:
        TerminalBenchMuxAdapter().load(tmp_path)

    assert "runs.parquet" in str(excinfo.value)


def test_adapter_load__missing_provenance_raises(tmp_path: Path) -> None:
    from eval_audit.ingest.base import IngestContractError

    submissions = {
        "Mux__GPT-5.3-Codex": _submission("openai/gpt-5.3-codex", "GPT-5.3 Codex"),
        "Mux__Claude-Opus-4.6": _submission(
            "anthropic/claude-opus-4-6", "Claude Opus 4.6"
        ),
    }
    frame = build_canonical_frame(submissions=submissions)
    frame.write_parquet(tmp_path / "runs.parquet")

    with pytest.raises(IngestContractError) as excinfo:
        TerminalBenchMuxAdapter().load(tmp_path)

    assert "provenance" in str(excinfo.value).lower()


def test_adapter_load__committed_fixture_contract(repo_root: Path) -> None:
    fixture_dir = repo_root / "examples" / "terminal-bench-2-mux"
    frame = TerminalBenchMuxAdapter().load(fixture_dir)

    assert frame.height == (
        2 * TERMINAL_BENCH_2_RUNS_PER_AGENT * TERMINAL_BENCH_2_TASK_COUNT
    )
    assert frame["tokens_in"].sum() > 0
    by_agent = frame.group_by("agent_id").agg(
        pl.col("task_id").n_unique().alias("n_tasks"),
        pl.col("run_id").n_unique().alias("n_runs"),
    )
    assert (by_agent["n_tasks"] == TERMINAL_BENCH_2_TASK_COUNT).all()
    assert (by_agent["n_runs"] == TERMINAL_BENCH_2_RUNS_PER_AGENT).all()
