"""Tests for src/executor/fill_model.py."""

from __future__ import annotations

import math

import pytest

from src.executor.fill_model import simulate_aggressive_fill


def test_fills_at_top_of_book_when_depth_sufficient() -> None:
    result = simulate_aggressive_fill(
        ladder=[(100.0, 10.0)],
        notional_usd=500.0,
        fee_per_leg=0.0,
        reference_price=100.0,
    )
    assert result.filled is True
    assert result.fill_price == pytest.approx(100.0)
    assert result.insufficient_depth is False


def test_walks_through_multiple_levels() -> None:
    result = simulate_aggressive_fill(
        ladder=[(100.0, 1.0), (101.0, 5.0)],
        notional_usd=600.0,  # 100*1 + 500 from second level (4.95 units)
        fee_per_leg=0.0,
        reference_price=100.0,
    )
    assert result.filled is True
    # VWAP should be between 100 and 101, closer to 101
    assert 100.0 < result.fill_price < 101.0


def test_insufficient_depth_returns_failure() -> None:
    result = simulate_aggressive_fill(
        ladder=[(100.0, 1.0)],  # only $100 of liquidity
        notional_usd=500.0,
        fee_per_leg=0.0,
        reference_price=100.0,
    )
    assert result.filled is False
    assert result.insufficient_depth is True


def test_empty_ladder_is_failure() -> None:
    result = simulate_aggressive_fill(
        ladder=[], notional_usd=100.0,
        fee_per_leg=0.0, reference_price=100.0,
    )
    assert result.filled is False


def test_fees_reduce_realised_return() -> None:
    r_no_fee = simulate_aggressive_fill(
        ladder=[(100.0, 10.0)], notional_usd=500.0,
        fee_per_leg=0.0, reference_price=100.0,
    )
    r_with_fee = simulate_aggressive_fill(
        ladder=[(100.0, 10.0)], notional_usd=500.0,
        fee_per_leg=0.001, reference_price=100.0,
    )
    assert r_with_fee.realised_log_return < r_no_fee.realised_log_return