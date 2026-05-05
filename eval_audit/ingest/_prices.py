"""Pinned provider prices for cost reconstruction.

Snapshotted at the scouting decision date (2026-05-02) per the locked
classification in scouting/exhibit-a-decision.md. Re-fetching live prices is
forbidden — that would silently break the `reconciled` invariant whenever a
provider changes pricing. Refreshing prices requires updating this constant
and the residual-risks copy together.
"""

from __future__ import annotations

PRICE_TABLE_PINNED_AT = "2026-05-02"

# (input_price_per_million, output_price_per_million) in USD.
# Sourced from scouting/candidates/gaia/cost-reconciliation.json `provider_pricing_source`.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "o4-mini-2025-04-16":         (1.10, 4.40),
    "claude-3-7-sonnet-20250219": (3.00, 15.00),
    "gpt-4o-2024-11-20":          (2.50, 10.00),
}
