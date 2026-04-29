"""Statistical methods for binary outcomes, paired comparisons, and frontier analysis."""

from rigor.stats.analyze import (
    AgentSummary,
    AnalysisResult,
    ClaimResult,
    CrossHarnessComparisonError,
    analyze,
)
from rigor.stats.bootstrap import BootstrapResult, paired_task_bootstrap
from rigor.stats.correction import holm_bonferroni
from rigor.stats.intervals import wilson_interval
from rigor.stats.pareto import pareto_frontier

__all__ = [
    "AgentSummary",
    "AnalysisResult",
    "BootstrapResult",
    "ClaimResult",
    "CrossHarnessComparisonError",
    "analyze",
    "holm_bonferroni",
    "paired_task_bootstrap",
    "pareto_frontier",
    "wilson_interval",
]
