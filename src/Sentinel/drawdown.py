"""Drawdown halt: pauses trading when rolling 24h P&L breaches a 2σ tripwire.

Reference: TECHNICAL_PLAN.md §6
Per AGENTS.md §5, resumption requires a [HALT-ACK] PR.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable

WINDOW_HOURS: int = 24
DEFAULT_SIGMA_MULTIPLIER: float = 2.0
MIN_SAMPLES_FOR_HALT: int = 10


@dataclass(frozen=True)
class DrawdownResult:
    halted: bool
    rolling_pnl_usd: float
    mu_usd: float
    sigma_usd: float
    tripwire_usd: float
    reason: str | None


def evaluate_drawdown(
    realised_pnl_window: Iterable[float],
    sigma_multiplier: float = DEFAULT_SIGMA_MULTIPLIER,
) -> DrawdownResult:
    """Decide whether trading should halt based on rolling P&L.

    Args:
        realised_pnl_window: post-fee P&L values from trades in the
            last `WINDOW_HOURS`. One value per trade.
        sigma_multiplier: tripwire is at (mu - k*sigma).
    """
    pnls = list(realised_pnl_window)
    if len(pnls) < MIN_SAMPLES_FOR_HALT:
        return DrawdownResult(
            halted=False,
            rolling_pnl_usd=sum(pnls),
            mu_usd=0.0,
            sigma_usd=0.0,
            tripwire_usd=-math.inf,
            reason=None,
        )

    mu = statistics.fmean(pnls)
    sigma = statistics.pstdev(pnls)
    tripwire = mu - sigma_multiplier * sigma
    total = sum(pnls)
    halted = total < tripwire

    return DrawdownResult(
        halted=halted,
        rolling_pnl_usd=total,
        mu_usd=mu,
        sigma_usd=sigma,
        tripwire_usd=tripwire,
        reason="drawdown_below_tripwire" if halted else None,
    )
