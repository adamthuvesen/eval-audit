"""Markdown report rendering for declared-claim reanalyses."""


class ReportContractError(RuntimeError):
    """Raised when the renderer is asked to emit content that violates the controlled vocabulary."""


__all__ = ["ReportContractError"]
