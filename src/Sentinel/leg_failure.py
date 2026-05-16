"""Leg-failure protocol: simulate the cost of unwinding an unwanted
position when a triangular cycle fails mid-execution.

Reference: TECHNICAL_PLAN.md §6 (Sentinel)

Scenario:
    Cycle USDT → BTC → ETH → USDT. Leg 1 fills (we now hold BTC).
    Leg 2 fails (the ETH/BTC quote moved or had insufficient depth).
    We are stuck with BTC; we unwind to USDT at the prevailing market.

This module computes the simulated unwind cost from the order book
at the moment the leg failed. Each result becomes a labeled negative
example for v2 of the Guardian (closed feedback loop per §6).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegFailureResult:
    unwound: bool
    unwind_cost_usd: float       # signed: negative = realised loss
    insufficient_depth: bool
    max_loss_tag: str            # audit label


def compute_unwind_cost(
    currency_held: str,
    quantity: float,
    market_bid_px: float,
    market_bid_sz: float,
    expected_value_usd: float,
) -> LegFailureResult:
    """Simulate selling `quantity` of `currency_held` at the market bid.

    Args:
        currency_held: the unwanted currency we're stuck with.
        quantity: position size in `currency_held` units.
        market_bid_px: top-of-book bid for currency_held/USDT pair.
        market_bid_sz: top-of-book bid size.
        expected_value_usd: position value at the time of fill (USD).

    Returns:
        LegFailureResult with realised value vs expected, plus an audit
        tag describing the outcome.
    """
    if quantity <= 0:
        return LegFailureResult(
            unwound=True,
            unwind_cost_usd=0.0,
            insufficient_depth=False,
            max_loss_tag="zero_position",
        )

    if market_bid_sz < quantity:
        # Top-of-book can't absorb the full position. v1 reports the
        # worst-case (only the top-of-book absorbed); v2 would walk
        # the bid ladder.
        realised_value = market_bid_sz * market_bid_px
        return LegFailureResult(
            unwound=False,
            unwind_cost_usd=realised_value - expected_value_usd,
            insufficient_depth=True,
            max_loss_tag="partial_unwind",
        )

    realised_value = quantity * market_bid_px
    return LegFailureResult(
        unwound=True,
        unwind_cost_usd=realised_value - expected_value_usd,
        insufficient_depth=False,
        max_loss_tag="clean_unwind",
    )
