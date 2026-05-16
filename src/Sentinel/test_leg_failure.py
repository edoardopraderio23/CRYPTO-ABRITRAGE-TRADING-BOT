"""Tests for src/sentinel/leg_failure.py."""

from __future__ import annotations

from src.sentinel.leg_failure import compute_unwind_cost


def test_clean_unwind_when_depth_sufficient() -> None:
    result = compute_unwind_cost(
        currency_held="BTC",
        quantity=0.01,
        market_bid_px=60_000.0,
        market_bid_sz=1.0,
        expected_value_usd=600.0,
    )
    assert result.unwound is True
    assert result.max_loss_tag == "clean_unwind"
    assert result.unwind_cost_usd == 0.0  # 0.01 * 60000 == expected


def test_partial_unwind_when_depth_insufficient() -> None:
    result = compute_unwind_cost(
        currency_held="BTC",
        quantity=1.0,
        market_bid_px=60_000.0,
        market_bid_sz=0.1,
        expected_value_usd=60_000.0,
    )
    assert result.unwound is False
    assert result.insufficient_depth is True
    assert result.max_loss_tag == "partial_unwind"


def test_realised_loss_when_market_drops() -> None:
    """0.01 BTC at $59 000 unwinds to $590; expected $600; loss = -$10."""
    result = compute_unwind_cost(
        currency_held="BTC",
        quantity=0.01,
        market_bid_px=59_000.0,
        market_bid_sz=1.0,
        expected_value_usd=600.0,
    )
    assert result.unwind_cost_usd == -10.0


def test_zero_quantity_is_noop() -> None:
    result = compute_unwind_cost(
        currency_held="BTC",
        quantity=0.0,
        market_bid_px=60_000.0,
        market_bid_sz=1.0,
        expected_value_usd=0.0,
    )
    assert result.unwound is True
    assert result.unwind_cost_usd == 0.0
    assert result.max_loss_tag == "zero_position"
