"""Shared markdown number formatting."""

from __future__ import annotations


def format_pp(delta: float) -> str:
    return f"{delta * 100:+.2f} pp"


def format_currency(value: float) -> str:
    return f"${value:.2f}"


def format_rate(value: float) -> str:
    return f"{value:.4f}"
