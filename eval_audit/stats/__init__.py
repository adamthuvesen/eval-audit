"""Statistical methods for binary outcomes, paired comparisons, and frontier analysis."""

from eval_audit.stats.analyze import (
    AgentSummary,
    AnalysisResult,
    ClaimResult,
    CrossHarnessComparisonError,
    UnsupportedOutcomeError,
    analyze,
)
from eval_audit.stats.bootstrap import BootstrapResult, paired_task_bootstrap
from eval_audit.stats.correction import benjamini_hochberg, holm_bonferroni
from eval_audit.stats.intervals import wilson_interval
from eval_audit.stats.pareto import pareto_frontier

__all__ = [
    "AgentSummary",
    "AnalysisResult",
    "BootstrapResult",
    "ClaimResult",
    "CrossHarnessComparisonError",
    "UnsupportedOutcomeError",
    "analyze",
    "benjamini_hochberg",
    "holm_bonferroni",
    "paired_task_bootstrap",
    "pareto_frontier",
    "wilson_interval",
]
