"""Acceptance tests for Holm-Bonferroni correction."""

from __future__ import annotations


def test_holm__family_of_one_collapses_to_identity() -> None:
    """WHEN the procedure is applied to a single (claim_id, raw_p=0.04) at alpha=0.05,
    THEN the adjusted p equals the raw p and reject == True.
    """
    from rigor.stats import holm_bonferroni

    result = holm_bonferroni([("c1", 0.04)], alpha=0.05)
    assert len(result) == 1
    claim_id, raw_p, adj_p, reject = result[0]
    assert claim_id == "c1"
    assert raw_p == 0.04
    assert adj_p == 0.04
    assert reject is True


def test_holm__step_down_monotonicity_holds() -> None:
    """WHEN the procedure is applied to claims with raw p [0.01, 0.04, 0.03] at alpha=0.05,
    THEN the adjusted p-values are monotonically non-decreasing in raw-p rank.
    """
    from rigor.stats import holm_bonferroni

    result = holm_bonferroni(
        [("a", 0.01), ("b", 0.04), ("c", 0.03)],
        alpha=0.05,
    )
    by_id = {claim_id: adj_p for claim_id, _, adj_p, _ in result}
    # Sorted by raw p ascending: a(0.01) < c(0.03) < b(0.04)
    assert by_id["a"] <= by_id["c"] <= by_id["b"]
