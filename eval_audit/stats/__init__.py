"""Statistical methods for binary outcomes, paired comparisons, and frontier analysis."""

from eval_audit.stats.agent_metrics import (
    ErroredRowPolicy,
    summarize_agent,
    summarize_agents_for_pareto,
)
from eval_audit.stats.analyze import (
    analyze,
    paired_task_p_value,
)
from eval_audit.stats.bootstrap import BootstrapResult, paired_task_bootstrap
from eval_audit.stats.correction import benjamini_hochberg, holm_bonferroni
from eval_audit.stats.errors import (
    AnalysisInputError,
    CostProvenanceError,
    CrossHarnessComparisonError,
    UnsupportedOutcomeError,
)
from eval_audit.stats.intervals import wilson_interval
from eval_audit.stats.pareto import pareto_frontier
from eval_audit.stats.resolution import (
    ResolutionEstimate,
    estimate_required_paired_tasks,
)
from eval_audit.stats.results import (
    AgentSummary,
    AnalysisResult,
    ClaimResult,
    ParetoStatus,
)

__all__ = [
    "AgentSummary",
    "AnalysisInputError",
    "AnalysisResult",
    "BootstrapResult",
    "ClaimResult",
    "CostProvenanceError",
    "CrossHarnessComparisonError",
    "ErroredRowPolicy",
    "ParetoStatus",
    "ResolutionEstimate",
    "UnsupportedOutcomeError",
    "analyze",
    "benjamini_hochberg",
    "estimate_required_paired_tasks",
    "holm_bonferroni",
    "paired_task_bootstrap",
    "paired_task_p_value",
    "pareto_frontier",
    "summarize_agent",
    "summarize_agents_for_pareto",
    "wilson_interval",
]
