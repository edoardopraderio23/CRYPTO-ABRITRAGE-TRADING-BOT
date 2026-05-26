"""Aggressive-fill simulator.

Walks displayed depth-5 ladder until the requested notional is
absorbed, applies the per-leg taker fee, and returns the realised
log-return relative to a reference price.

Reference: TECHNICAL_PLAN.md §8 (fill model assumptions).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class FillResult:
    filled: bool
    fill_price: float
    realised_log_return: float
    insufficient_depth: bool


def simulate_aggressive_fill(
    ladder: list[tuple[float, float]],
    notional_usd: float,
    fee_per_leg: float,
    reference_price: float,
) -> FillResult:
    """Walk `ladder` until `notional_usd` of value is filled.

    Args:
        ladder: list of (price, size) tuples, depth-5 typically.
        notional_usd: USD value we need to absorb.
        fee_per_leg: taker fee, e.g. 0.001 for 10 bps.
        reference_price: mid at signal time, for log-return calculation.

    Returns:
        FillResult. `realised_log_return` is post-fee for one leg.
    """
    if not ladder or reference_price <= 0 or notional_usd <= 0:
        return FillResult(False, 0.0, -math.inf, True)

    remaining_value = notional_usd
    total_value = 0.0
    total_quantity = 0.0

    for price, size in ladder:
        level_value = price * size
        take_value = min(remaining_value, level_value)
        take_qty = take_value / price
        total_value += take_value
        total_quantity += take_qty
        remaining_value -= take_value
        if remaining_value <= 1e-9:
            break

    if remaining_value > 1e-9:
        return FillResult(False, 0.0, -math.inf, True)

    fill_price = total_value / total_quantity
    realised = math.log(reference_price / fill_price * (1.0 - fee_per_leg))

    return FillResult(
        filled=True,
        fill_price=fill_price,
        realised_log_return=realised,
        insufficient_depth=False,
    )