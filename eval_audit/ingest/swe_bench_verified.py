"""Adapter for the SWE-bench Verified public-submission audit family.

Loads paired public submissions from the `swe-bench/experiments` repository
into canonical RunRecord rows under the SWE-bench Verified 500-task universe.
This adapter is the cost-suppressed counterpart to HAL adapters: the upstream
`results.json` artifacts expose only `resolved` / `no_generation` / `no_logs`
sets keyed by `instance_id`, with no stable token, usage, or cost fields.

Every emitted row carries `cost_provenance="cost_not_available"` and null
cost fields. The adapter never fabricates cost. Tokens are recorded as zero
with empty per-model breakdowns; the cost-not-available provenance class
forces the report to suppress every cost-derived view, so zero tokens are
read by the renderer as "no token data" rather than as a real measurement.

The adapter is fixture-driven: it loads the canonical parquet committed at
`examples/swe-bench-verified-openhands/runs.parquet`. The regenerator script
at `tools/regenerate_swe_bench_verified.py` produces this fixture from public
artifacts.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from eval_audit.ingest.base import IngestContractError, validate_run_records
from eval_audit.schema.enums import CostProvenance

SWE_BENCH_VERIFIED_TASK_COUNT = 500
SWE_BENCH_VERIFIED_HARNESS = "swe-bench-verified/openhands-public-submission-v1"

# RunRecord declares tokens_in_by_model: dict[str, int]. Polars cannot write a
# struct column to parquet with no child fields, so an all-empty dict column
# fails parquet round-trip. Emit a single sentinel entry documenting that
# tokens are unavailable upstream. The renderer never iterates these dicts
# for cost-suppressed studies; the schema stays valid (dict[str, int] with
# one entry); a reader can grep for this sentinel.
_TOKENS_UNAVAILABLE_SENTINEL: dict[str, int] = {"upstream_tokens_unavailable": 0}


class SweBenchVerifiedAdapter:
    """Loads the committed SWE-bench Verified OpenHands paired-submission parquet."""

    name = "swe_bench_verified"

    def load(self, source_path: Path) -> pl.DataFrame:
        """Load the canonical RunRecord parquet from the committed fixture directory.

        `source_path` MUST be a directory containing `runs.parquet` and
        `provenance.json`. The provenance file is required so a reader can
        always trace back to the upstream artifacts and pinned commit.
        """
        source_path = Path(source_path)
        runs_path = source_path / "runs.parquet"
        provenance_path = source_path / "provenance.json"
        if not runs_path.exists():
            raise IngestContractError(
                f"swe_bench_verified adapter requires {runs_path}"
            )
        if not provenance_path.exists():
            raise IngestContractError(
                f"swe_bench_verified adapter requires {provenance_path}; "
                "regenerate the fixture with tools/regenerate_swe_bench_verified.py"
            )
        frame = pl.read_parquet(runs_path)
        self.validate(frame)
        return frame

    def validate(self, frame: pl.DataFrame) -> None:
        validate_run_records(frame)
        if "harness" in frame.columns and not (
            frame["harness"] == SWE_BENCH_VERIFIED_HARNESS
        ).all():
            harnesses = sorted(frame["harness"].unique().to_list())
            raise IngestContractError(
                "swe_bench_verified adapter expects every row to have "
                f"harness={SWE_BENCH_VERIFIED_HARNESS!r}; got {harnesses}"
            )
        if "cost_provenance" in frame.columns and not (
            frame["cost_provenance"] == CostProvenance.COST_NOT_AVAILABLE.value
        ).all():
            classes = sorted(frame["cost_provenance"].unique().to_list())
            raise IngestContractError(
                "swe_bench_verified adapter expects every row to have "
                f"cost_provenance='cost_not_available'; got {classes}"
            )
        if frame["reconstructed_per_task_cost_usd"].null_count() != frame.height:
            raise IngestContractError(
                "swe_bench_verified adapter expects every row to have null "
                "reconstructed_per_task_cost_usd; cost is not available upstream"
            )
        if frame["reported_run_total_cost_usd"].null_count() != frame.height:
            raise IngestContractError(
                "swe_bench_verified adapter expects every row to have null "
                "reported_run_total_cost_usd; cost is not available upstream"
            )
        # Universe contract: each agent must cover exactly the SWE-bench Verified
        # 500-task universe with no duplicates, and every agent must share that
        # same task set. A truncated, duplicate, or mismatched fixture would
        # silently produce a non-500-task audit; fail loudly here.
        agent_task_sets: dict[str, set[str]] = {}
        for agent_id, group in frame.group_by("agent_id"):
            agent_id_str = str(agent_id[0]) if isinstance(agent_id, tuple) else str(agent_id)
            task_ids = group["task_id"].to_list()
            unique_tasks = set(task_ids)
            if len(task_ids) != len(unique_tasks):
                duplicates = sorted(
                    {t for t in task_ids if task_ids.count(t) > 1}
                )[:3]
                raise IngestContractError(
                    f"swe_bench_verified adapter found duplicate task_ids for "
                    f"agent_id={agent_id_str!r} (first 3: {duplicates}); each "
                    "agent must contribute exactly one row per task"
                )
            if len(unique_tasks) != SWE_BENCH_VERIFIED_TASK_COUNT:
                raise IngestContractError(
                    f"swe_bench_verified adapter expects each agent to cover "
                    f"{SWE_BENCH_VERIFIED_TASK_COUNT} unique task_ids; "
                    f"agent_id={agent_id_str!r} covers {len(unique_tasks)}"
                )
            agent_task_sets[agent_id_str] = unique_tasks
        reference_universe: set[str] | None = None
        reference_agent: str | None = None
        for agent_id_str, task_set in agent_task_sets.items():
            if reference_universe is None:
                reference_universe = task_set
                reference_agent = agent_id_str
                continue
            if task_set != reference_universe:
                missing = sorted(reference_universe - task_set)[:3]
                extra = sorted(task_set - reference_universe)[:3]
                raise IngestContractError(
                    f"swe_bench_verified adapter expects every agent to share "
                    f"the same 500-task universe; agent_id={agent_id_str!r} "
                    f"differs from agent_id={reference_agent!r} "
                    f"(first 3 missing: {missing}; first 3 extra: {extra})"
                )


def build_canonical_frame(
    *,
    task_universe: list[str],
    submissions: dict[str, dict],
) -> pl.DataFrame:
    """Build a canonical RunRecord frame from a task universe and submission dicts.

    Each entry in ``submissions`` MUST be keyed by the submission's agent_id
    (matching the directory name under `swe-bench/experiments/evaluation/verified/`)
    and carry:

    - ``model_id`` (str): the model line from the submission's README.
    - ``submission_dir`` (str): for `rerun_metadata`.
    - ``resolved`` (set[str]): instance_ids in the submission's `resolved` list.
    - ``no_generation`` (set[str]): instance_ids in `no_generation`.
    - ``no_logs`` (set[str]): instance_ids in `no_logs`.

    The returned frame contains exactly ``len(task_universe) × len(submissions)``
    rows. Resolved instances become success=True; no_generation / no_logs
    become graded failures with `rerun_metadata.upstream_status` set
    accordingly. All other tasks become success=False (graded failure with no
    upstream classifier).

    The function is pure (no I/O) so tests and the regenerator can both build
    canonical frames without re-reading upstream files.
    """
    if len(task_universe) != SWE_BENCH_VERIFIED_TASK_COUNT:
        raise IngestContractError(
            f"SWE-bench Verified task universe must have "
            f"{SWE_BENCH_VERIFIED_TASK_COUNT} rows; got {len(task_universe)}"
        )
    if len(set(task_universe)) != len(task_universe):
        raise IngestContractError(
            "SWE-bench Verified task universe contains duplicate instance_ids"
        )

    rows: list[dict] = []
    for agent_id, submission in submissions.items():
        resolved: set[str] = set(submission["resolved"])
        no_generation: set[str] = set(submission.get("no_generation", []))
        no_logs: set[str] = set(submission.get("no_logs", []))
        model_id: str = submission["model_id"]
        submission_dir: str = submission["submission_dir"]

        universe_set = set(task_universe)
        for set_name, status_set in (
            ("resolved", resolved),
            ("no_generation", no_generation),
            ("no_logs", no_logs),
        ):
            unknown = status_set - universe_set
            if unknown:
                raise IngestContractError(
                    f"submission {agent_id!r} {set_name} contains unknown "
                    f"instance_ids (first 3: {sorted(unknown)[:3]})"
                )

        # Status sets must be pairwise disjoint. Without this guard, the
        # if/elif chain below silently picks resolved over no_generation /
        # no_logs and turns an upstream contradiction into a success row.
        for set_a_name, set_a, set_b_name, set_b in (
            ("resolved", resolved, "no_generation", no_generation),
            ("resolved", resolved, "no_logs", no_logs),
            ("no_generation", no_generation, "no_logs", no_logs),
        ):
            overlap = set_a & set_b
            if overlap:
                raise IngestContractError(
                    f"submission {agent_id!r} has overlapping status sets "
                    f"{set_a_name} and {set_b_name} "
                    f"(first 3 overlapping instance_ids: {sorted(overlap)[:3]})"
                )

        for instance_id in task_universe:
            if instance_id in resolved:
                success = True
                upstream_status = "resolved"
            elif instance_id in no_generation:
                success = False
                upstream_status = "no_generation"
            elif instance_id in no_logs:
                success = False
                upstream_status = "no_logs"
            else:
                success = False
                upstream_status = "graded_failure"
            rows.append(
                {
                    "agent_id": agent_id,
                    "model_id": model_id,
                    "harness": SWE_BENCH_VERIFIED_HARNESS,
                    "run_id": agent_id,
                    "task_id": instance_id,
                    "task_category": None,
                    "seed": None,
                    "success": success,
                    "partial_credit": None,
                    "outcome_status": "graded",
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "tokens_in_by_model": dict(_TOKENS_UNAVAILABLE_SENTINEL),
                    "tokens_out_by_model": dict(_TOKENS_UNAVAILABLE_SENTINEL),
                    "latency_s": None,
                    "timestamp": None,
                    "reconstructed_per_task_cost_usd": None,
                    "reported_run_total_cost_usd": None,
                    "cost_provenance": CostProvenance.COST_NOT_AVAILABLE.value,
                    "rerun_metadata": {
                        "submission_dir": submission_dir,
                        "upstream_status": upstream_status,
                    },
                }
            )
    return pl.DataFrame(rows, strict=False)
