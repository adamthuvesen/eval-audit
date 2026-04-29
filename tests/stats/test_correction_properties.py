"""Property-based tests for Holm-Bonferroni correction invariants."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rigor.stats import benjamini_hochberg, holm_bonferroni

_SETTINGS = settings(max_examples=100, deadline=2_000)


def _claim_family(min_size: int = 1, max_size: int = 20) -> st.SearchStrategy:
    """A list of (claim_id, raw_p) pairs with unique ids."""
    return st.lists(
        st.tuples(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=8),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=min_size,
        max_size=max_size,
        unique_by=lambda item: item[0],
    )


@_SETTINGS
@given(_claim_family())
def test_holm__monotonicity_in_raw_p_rank(claims: list) -> None:
    """Adjusted p-values are monotonically non-decreasing in sorted-by-raw-p rank."""
    result = holm_bonferroni(claims, alpha=0.05)
    by_id = {cid: (rp, ap) for cid, rp, ap, _ in result}
    sorted_ids = sorted(by_id, key=lambda cid: by_id[cid][0])
    adj_in_order = [by_id[cid][1] for cid in sorted_ids]
    for prev, curr in zip(adj_in_order, adj_in_order[1:], strict=False):
        assert prev <= curr + 1e-12, (
            f"adjusted p-values not non-decreasing in raw-p rank: {adj_in_order}"
        )


@_SETTINGS
@given(_claim_family(), st.floats(min_value=0.001, max_value=0.5))
def test_holm__adjusted_p_in_unit_interval(claims: list, alpha: float) -> None:
    """Every adjusted p-value lies in [0, 1]."""
    result = holm_bonferroni(claims, alpha=alpha)
    for _, _, adj_p, _ in result:
        assert 0.0 <= adj_p <= 1.0, f"adjusted p {adj_p} not in [0, 1]"


@_SETTINGS
@given(_claim_family(min_size=1, max_size=10))
def test_holm__idempotent_when_re_applied_to_raw_p(claims: list) -> None:
    """Running holm twice over the same (claim_id, raw_p) pairs gives the same adjusted_p."""
    a = holm_bonferroni(claims, alpha=0.05)
    raw_again = [(cid, rp) for cid, rp, _, _ in a]
    b = holm_bonferroni(raw_again, alpha=0.05)
    a_adj = {cid: ap for cid, _, ap, _ in a}
    b_adj = {cid: ap for cid, _, ap, _ in b}
    assert a_adj == b_adj


def test_holm__family_of_one_is_identity() -> None:
    """A single-claim family adjusts to the raw p-value (already covered as example, kept for parity)."""
    [(_, raw, adj, _)] = holm_bonferroni([("only", 0.04)], alpha=0.05)
    assert raw == adj == 0.04


@_SETTINGS
@given(_claim_family())
def test_bh__monotonicity_in_raw_p_rank(claims: list) -> None:
    """BH adjusted p-values are monotonically non-decreasing in sorted-by-raw-p rank."""
    result = benjamini_hochberg(claims, alpha=0.05)
    by_id = {cid: (rp, ap) for cid, rp, ap, _ in result}
    sorted_ids = sorted(by_id, key=lambda cid: by_id[cid][0])
    adj_in_order = [by_id[cid][1] for cid in sorted_ids]
    for prev, curr in zip(adj_in_order, adj_in_order[1:], strict=False):
        assert prev <= curr + 1e-12


@_SETTINGS
@given(_claim_family(), st.floats(min_value=0.001, max_value=0.5))
def test_bh__adjusted_p_in_unit_interval(claims: list, alpha: float) -> None:
    """Every BH adjusted p-value lies in [0, 1]."""
    result = benjamini_hochberg(claims, alpha=alpha)
    for _, _, adj_p, _ in result:
        assert 0.0 <= adj_p <= 1.0
