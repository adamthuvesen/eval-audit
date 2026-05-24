"""Multiple-comparison correction procedures."""

from __future__ import annotations


def holm_bonferroni(
    claims: list[tuple[str, float]],
    *,
    alpha: float = 0.05,
) -> list[tuple[str, float, float, bool]]:
    """Apply Holm-Bonferroni step-down to (claim_id, raw_p) pairs.

    Returns (claim_id, raw_p, adjusted_p, reject) tuples in the original input order.
    """
    if not claims:
        return []

    indexed = list(enumerate(claims))
    sorted_by_p = sorted(indexed, key=lambda item: item[1][1])
    m = len(claims)

    adjusted: dict[int, float] = {}
    running_max = 0.0
    for rank, (orig_idx, (_claim_id, raw_p)) in enumerate(sorted_by_p, start=1):
        adj = min(1.0, (m - rank + 1) * raw_p)
        running_max = max(running_max, adj)
        adjusted[orig_idx] = running_max

    return [
        (claim_id, raw_p, adjusted[idx], adjusted[idx] <= alpha)
        for idx, (claim_id, raw_p) in enumerate(claims)
    ]


def benjamini_hochberg(
    claims: list[tuple[str, float]],
    *,
    alpha: float = 0.05,
) -> list[tuple[str, float, float, bool]]:
    """Apply Benjamini-Hochberg FDR correction to (claim_id, raw_p) pairs.

    Returns (claim_id, raw_p, adjusted_p, reject) tuples in the original input order.
    """
    if not claims:
        return []

    indexed = list(enumerate(claims))
    sorted_by_p = sorted(indexed, key=lambda item: item[1][1])
    m = len(claims)

    adjusted: dict[int, float] = {}
    running_min = 1.0
    for rank, (orig_idx, (_claim_id, raw_p)) in reversed(list(enumerate(sorted_by_p, start=1))):
        adj = min(1.0, (m / rank) * raw_p)
        running_min = min(running_min, adj)
        adjusted[orig_idx] = running_min

    return [
        (claim_id, raw_p, adjusted[idx], adjusted[idx] <= alpha)
        for idx, (claim_id, raw_p) in enumerate(claims)
    ]
