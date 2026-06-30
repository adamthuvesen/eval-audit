"""Adapter for the Terminal-Bench 2.0 Mux public-submission audit.

Terminal-Bench leaderboard submissions publish one ``result.json`` per
task/trial under the Hugging Face leaderboard dataset. This adapter loads the
canonical RunRecord parquet committed at
``examples/terminal-bench-2-mux/runs.parquet``.

The public artifacts expose token counts but ``agent_result.cost_usd`` is not
complete across the selected submissions. Every emitted row therefore carries
``cost_provenance="cost_not_available"`` with null cost fields. The report
suppresses cost-derived views instead of deriving prices from an unstated cost
policy.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl

from eval_audit.ingest.base import IngestContractError, validate_run_records
from eval_audit.schema.enums import CostProvenance

TERMINAL_BENCH_2_TASK_COUNT = 89
TERMINAL_BENCH_2_RUNS_PER_AGENT = 5
TERMINAL_BENCH_2_HARNESS = "terminal-bench-2/mux-public-submission-v1"


class TerminalBenchMuxAdapter:
    """Load the committed Terminal-Bench 2.0 Mux public-submission fixture."""

    name = "terminal_bench_mux"

    def load(self, source_path: Path) -> pl.DataFrame:
        source_path = Path(source_path)
        runs_path = source_path / "runs.parquet"
        provenance_path = source_path / "provenance.json"
        if not runs_path.exists():
            raise IngestContractError(f"terminal_bench_mux adapter requires {runs_path}")
        if not provenance_path.exists():
            raise IngestContractError(
                f"terminal_bench_mux adapter requires {provenance_path}; "
                "regenerate the fixture with tools/regenerate_terminal_bench_mux.py"
            )
        frame = pl.read_parquet(runs_path)
        self.validate(frame)
        return frame

    def validate(self, frame: pl.DataFrame) -> None:
        validate_run_records(frame)
        _validate_harness(frame)
        _validate_cost_not_available(frame)
        _validate_shared_task_universe(_validated_agent_task_sets(frame))


def _validate_harness(frame: pl.DataFrame) -> None:
    if (frame["harness"] == TERMINAL_BENCH_2_HARNESS).all():
        return
    harnesses = sorted(frame["harness"].unique().to_list())
    raise IngestContractError(
        "terminal_bench_mux adapter expects every row to have "
        f"harness={TERMINAL_BENCH_2_HARNESS!r}; got {harnesses}"
    )


def _validate_cost_not_available(frame: pl.DataFrame) -> None:
    if not (frame["cost_provenance"] == CostProvenance.COST_NOT_AVAILABLE.value).all():
        classes = sorted(frame["cost_provenance"].unique().to_list())
        raise IngestContractError(
            "terminal_bench_mux adapter expects every row to have "
            f"cost_provenance='cost_not_available'; got {classes}"
        )
    if frame["reconstructed_per_task_cost_usd"].null_count() != frame.height:
        raise IngestContractError(
            "terminal_bench_mux adapter expects null reconstructed cost; "
            "cost is not available upstream"
        )
    if frame["reported_run_total_cost_usd"].null_count() != frame.height:
        raise IngestContractError(
            "terminal_bench_mux adapter expects null reported run cost; "
            "cost is not available upstream"
        )


def _validated_agent_task_sets(frame: pl.DataFrame) -> dict[str, set[str]]:
    agent_task_sets: dict[str, set[str]] = {}
    for agent_key, agent_rows in frame.group_by("agent_id"):
        agent_id = _group_key_to_str(agent_key)
        _validate_agent_runs(agent_id, agent_rows)
        agent_task_sets[agent_id] = set(agent_rows["task_id"].to_list())
    return agent_task_sets


def _validate_agent_runs(agent_id: str, agent_rows: pl.DataFrame) -> None:
    run_ids = sorted(agent_rows["run_id"].unique().to_list())
    if len(run_ids) != TERMINAL_BENCH_2_RUNS_PER_AGENT:
        raise IngestContractError(
            f"terminal_bench_mux adapter expects {TERMINAL_BENCH_2_RUNS_PER_AGENT} "
            f"run_ids per agent; agent_id={agent_id!r} has {len(run_ids)}"
        )
    for run_id in run_ids:
        _validate_run_task_coverage(agent_id, run_id, agent_rows)


def _validate_run_task_coverage(
    agent_id: str,
    run_id: object,
    agent_rows: pl.DataFrame,
) -> None:
    run_rows = agent_rows.filter(pl.col("run_id") == run_id)
    task_ids = run_rows["task_id"].to_list()
    unique_tasks = set(task_ids)
    if len(task_ids) != len(unique_tasks):
        raise IngestContractError(
            f"terminal_bench_mux adapter found duplicate task_ids "
            f"for agent_id={agent_id!r}, run_id={run_id!r}"
        )
    if len(unique_tasks) != TERMINAL_BENCH_2_TASK_COUNT:
        raise IngestContractError(
            f"terminal_bench_mux adapter expects each run to cover "
            f"{TERMINAL_BENCH_2_TASK_COUNT} unique task_ids; "
            f"agent_id={agent_id!r}, run_id={run_id!r} covers {len(unique_tasks)}"
        )


def _validate_shared_task_universe(agent_task_sets: dict[str, set[str]]) -> None:
    reference_agent: str | None = None
    reference_tasks: set[str] | None = None
    for agent_id, task_set in sorted(agent_task_sets.items()):
        if reference_tasks is None:
            reference_agent = agent_id
            reference_tasks = task_set
            continue
        if task_set == reference_tasks:
            continue
        missing = sorted(reference_tasks - task_set)[:3]
        extra = sorted(task_set - reference_tasks)[:3]
        raise IngestContractError(
            "terminal_bench_mux adapter expects every agent to share "
            f"the same task universe; agent_id={agent_id!r} differs "
            f"from agent_id={reference_agent!r} "
            f"(first 3 missing: {missing}; first 3 extra: {extra})"
        )


def build_canonical_frame(
    *,
    submissions: dict[str, dict],
    expected_task_count: int = TERMINAL_BENCH_2_TASK_COUNT,
    expected_runs_per_agent: int = TERMINAL_BENCH_2_RUNS_PER_AGENT,
) -> pl.DataFrame:
    """Build canonical RunRecord rows from parsed Terminal-Bench result JSON.

    ``submissions`` is keyed by leaderboard submission directory name. Each
    value must contain:

    - ``metadata``: parsed ``metadata.yaml`` for the submission.
    - ``runs``: mapping of ``run_id`` to a list of parsed result records.

    The function is pure so both tests and the network-backed regenerator can
    share the same outcome mapping.
    """
    rows: list[dict] = []
    reference_tasks: set[str] | None = None
    for agent_id, submission in submissions.items():
        submission_rows, agent_tasks = _canonical_submission_rows(
            agent_id,
            submission,
            expected_task_count=expected_task_count,
            expected_runs_per_agent=expected_runs_per_agent,
        )
        rows.extend(submission_rows)
        reference_tasks = _validate_reference_tasks(agent_id, agent_tasks, reference_tasks)

    frame = pl.DataFrame(rows, strict=False)
    TerminalBenchMuxAdapter().validate(frame)
    return frame


def _canonical_submission_rows(
    agent_id: str,
    submission: dict,
    *,
    expected_task_count: int,
    expected_runs_per_agent: int,
) -> tuple[list[dict], set[str]]:
    metadata = dict(submission.get("metadata") or {})
    runs = dict(submission["runs"])
    if len(runs) != expected_runs_per_agent:
        raise IngestContractError(
            f"Terminal-Bench submission {agent_id!r} must have "
            f"{expected_runs_per_agent} runs; got {len(runs)}"
        )

    rows: list[dict] = []
    agent_tasks: set[str] | None = None
    for run_id, records in sorted(runs.items()):
        unique_tasks = _validated_run_tasks(
            agent_id,
            run_id,
            records,
            expected_task_count=expected_task_count,
        )
        if agent_tasks is None:
            agent_tasks = unique_tasks
        elif unique_tasks != agent_tasks:
            raise IngestContractError(
                f"Terminal-Bench submission {agent_id!r} has mismatched "
                f"task sets across run_id={run_id!r}"
            )

        for record in sorted(records, key=lambda item: str(item["task_name"])):
            rows.append(_record_to_row(agent_id, run_id, metadata, record))

    if agent_tasks is None:
        raise IngestContractError(f"Terminal-Bench submission {agent_id!r} has no runs")
    return rows, agent_tasks


def _validated_run_tasks(
    agent_id: str,
    run_id: str,
    records: list[dict],
    *,
    expected_task_count: int,
) -> set[str]:
    task_ids = [str(record["task_name"]) for record in records]
    unique_tasks = set(task_ids)
    if len(task_ids) != len(unique_tasks):
        raise IngestContractError(
            f"Terminal-Bench submission {agent_id!r}, run_id={run_id!r} "
            "contains duplicate task_name values"
        )
    if len(unique_tasks) != expected_task_count:
        raise IngestContractError(
            f"Terminal-Bench submission {agent_id!r}, run_id={run_id!r} "
            f"must cover {expected_task_count} tasks; got {len(unique_tasks)}"
        )
    return unique_tasks


def _validate_reference_tasks(
    agent_id: str,
    agent_tasks: set[str],
    reference_tasks: set[str] | None,
) -> set[str]:
    if reference_tasks is None:
        return agent_tasks
    if agent_tasks == reference_tasks:
        return reference_tasks
    missing = sorted(reference_tasks - agent_tasks)[:3]
    extra = sorted(agent_tasks - reference_tasks)[:3]
    raise IngestContractError(
        f"Terminal-Bench submission {agent_id!r} does not share the "
        f"reference task universe (first 3 missing: {missing}; "
        f"first 3 extra: {extra})"
    )


def _record_to_row(
    agent_id: str,
    run_id: str,
    metadata: dict,
    record: dict,
) -> dict:
    agent_result = dict(record.get("agent_result") or {})
    config_agent = dict((record.get("config") or {}).get("agent") or {})
    model_id = str(config_agent.get("model_name") or metadata["model"]["name"])
    reward = _reward(record)
    outcome_status, success, partial_credit = _outcome_fields(reward)
    tokens_in, tokens_out = _token_counts(agent_result)
    started_at = _parse_timestamp(record.get("started_at"))
    finished_at = _parse_timestamp(record.get("finished_at"))
    task_id = str(record["task_name"])
    task_info = dict(record.get("task_id") or {})
    return {
        "agent_id": agent_id,
        "model_id": model_id,
        "harness": TERMINAL_BENCH_2_HARNESS,
        "run_id": run_id,
        "task_id": task_id,
        "task_category": None,
        "seed": None,
        "success": success,
        "partial_credit": partial_credit,
        "outcome_status": outcome_status,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_in_by_model": {model_id: tokens_in},
        "tokens_out_by_model": {model_id: tokens_out},
        "latency_s": _latency_s(started_at, finished_at),
        "timestamp": started_at,
        "reconstructed_per_task_cost_usd": None,
        "reported_run_total_cost_usd": None,
        "cost_provenance": CostProvenance.COST_NOT_AVAILABLE.value,
        "rerun_metadata": _rerun_metadata(
            metadata=metadata,
            config_agent=config_agent,
            record=record,
            task_info=task_info,
            agent_result=agent_result,
            reward=reward,
        ),
    }


def _outcome_fields(reward: float | None) -> tuple[str, bool | None, float | None]:
    if reward is None:
        return "errored", None, None
    return "graded", bool(float(reward) >= 1.0), float(reward)


def _token_counts(agent_result: dict) -> tuple[int, int]:
    return int(agent_result.get("n_input_tokens") or 0), int(
        agent_result.get("n_output_tokens") or 0
    )


def _latency_s(started_at: datetime | None, finished_at: datetime | None) -> float | None:
    if started_at is None or finished_at is None:
        return None
    return max((finished_at - started_at).total_seconds(), 0.0)


def _rerun_metadata(
    *,
    metadata: dict,
    config_agent: dict,
    record: dict,
    task_info: dict,
    agent_result: dict,
    reward: float | None,
) -> dict[str, str]:
    return {
        "agent_display_name": str(metadata.get("agent", {}).get("display_name", "")),
        "agent_import_path": str(config_agent.get("import_path") or ""),
        "model_display_name": str(metadata.get("model", {}).get("display_name", "")),
        "model_provider": str(metadata.get("model", {}).get("provider", "")),
        "source": str(record.get("source") or ""),
        "submission_path": str(record.get("_submission_path") or ""),
        "task_git_commit": str(task_info.get("git_commit_id") or ""),
        "task_git_url": str(task_info.get("git_url") or ""),
        "trial_name": str(record.get("trial_name") or ""),
        "upstream_reward": "" if reward is None else str(float(reward)),
        "upstream_cost_usd": str(agent_result.get("cost_usd")),
    }


def _reward(record: dict) -> float | None:
    verifier_result = record.get("verifier_result")
    if not isinstance(verifier_result, dict):
        return None
    rewards = verifier_result.get("rewards")
    if not isinstance(rewards, dict) or rewards.get("reward") is None:
        return None
    return float(rewards["reward"])


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _group_key_to_str(value: object) -> str:
    if isinstance(value, tuple):
        return str(value[0])
    return str(value)
