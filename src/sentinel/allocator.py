"""Capital allocator: distributes bankroll across exchanges using a
risk-adjusted opportunity score.

For each venue i, in a rolling lookback window:

    score_i = (freq_i * size_i * pass_rate_i) / sigma_i

where:
    freq_i      = cycles per second passing the Profit Gate
    size_i      = mean expected post-fee return per cycle, in basis points
    pass_rate_i = empirical pass rate of the Confidence Gate (0..1)
    sigma_i     = standard deviation of hourly post-fee P&L, in USD

Allocation rule:
    floor_i  = max_trade_size_usd * LEGS_PER_CYCLE   # one cycle's worth
    residual = bankroll_usd - sum(floor_i)
    w_i      = score_i / sum(score_j)                # normalised, >= 0
    cap_i    = floor_i + residual * w_i

Reference: TECHNICAL_PLAN.md (capital allocation), AGENTS.md §4
(human-in-the-loop review for `src/sentinel/`).

[AI-AGENT-CONTRIBUTION] Generated 2026-05-07 by Claude.
See PR description and `docs/prompts/2026-05-07_sentinel_allocator.md`
for prompt provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import structlog

log = structlog.get_logger(__name__)

# Number of legs in a triangular arbitrage cycle. Used to size the
# operational floor: each venue must hold enough capital for all
# three legs to fill simultaneously.
LEGS_PER_CYCLE: int = 3


@dataclass(frozen=True)
class VenueMetrics:
    """Rolling-window summary statistics for a single exchange.

    All values are computed by the caller (typically a nightly job
    that queries `cycles_detected` and `trades_simulated` from the
    last 24 hours).
    """

    freq_per_sec: float
    """Cycles per second passing the Profit Gate."""

    avg_size_bps: float
    """Mean expected post-fee return per cycle, in basis points."""

    pass_rate: float
    """Fraction passing the Confidence Gate, in [0, 1]."""

    pnl_sigma_usd: float
    """Standard deviation of hourly post-fee P&L, in USD."""


@dataclass(frozen=True)
class AllocationResult:
    """Output of one allocator run, suitable for persistence and audit."""

    capital: Mapping[str, float]
    """venue -> USD allocated"""

    scores: Mapping[str, float]
    """venue -> raw risk-adjusted opportunity score (post-clamp)"""

    weights: Mapping[str, float]
    """venue -> normalised weight in [0, 1]; sums to 1"""

    rationale: str
    """Human-readable summary, written to `capital_allocations.rationale`."""


def _venue_score(m: VenueMetrics) -> float:
    """Sharpe-like score for one venue.

    Returns 0 if the venue has zero or negative expected revenue, or
    if its volatility is non-positive (no historical data, can't size
    risk). Clamping to zero is the audit-friendly behaviour: a venue
    with insufficient history simply receives only its operational
    floor, never a slice of the residual.
    """
    if m.pnl_sigma_usd <= 0:
        return 0.0
    raw = m.freq_per_sec * m.avg_size_bps * m.pass_rate
    if raw <= 0:
        return 0.0
    return raw / m.pnl_sigma_usd


def allocate(
    venue_metrics: Mapping[str, VenueMetrics],
    bankroll_usd: float,
    max_trade_size_usd: float,
) -> AllocationResult:
    """Distribute bankroll across venues with floor + opportunity weight.

    Args:
        venue_metrics: rolling-window stats per venue, keyed by venue name.
        bankroll_usd: total paper-trade capital available across all venues.
        max_trade_size_usd: max single-trade notional. Each venue gets a
            floor of (max_trade_size_usd * LEGS_PER_CYCLE) so it can fire
            at least one full triangular cycle.

    Returns:
        AllocationResult with capital, scores, weights, and audit rationale.

    Raises:
        ValueError: if no venues are provided, if bankroll or max trade
            size is non-positive, or if bankroll is too small to fund
            every venue's operational floor.
    """
    if not venue_metrics:
        raise ValueError("venue_metrics must not be empty")
    if bankroll_usd <= 0:
        raise ValueError(f"bankroll_usd must be positive, got {bankroll_usd}")
    if max_trade_size_usd <= 0:
        raise ValueError(
            f"max_trade_size_usd must be positive, got {max_trade_size_usd}"
        )

    n_venues = len(venue_metrics)
    floor_per_venue = max_trade_size_usd * LEGS_PER_CYCLE
    total_floor = floor_per_venue * n_venues

    if total_floor > bankroll_usd:
        raise ValueError(
            f"bankroll_usd={bankroll_usd:.2f} too small to fund "
            f"{n_venues} venues at floor={floor_per_venue:.2f} each "
            f"(needed {total_floor:.2f})"
        )

    residual = bankroll_usd - total_floor

    scores = {v: _venue_score(m) for v, m in venue_metrics.items()}
    total_score = sum(scores.values())

    if total_score <= 0:
        # Fall back to equal-weight split. Audit-defensible: when the
        # data says nothing, we treat venues symmetrically rather than
        # picking one by tie-break.
        equal_weight = 1.0 / n_venues
        weights = {v: equal_weight for v in venue_metrics}
        rationale = (
            f"All venues scored 0 (insufficient or unprofitable history). "
            f"Equal-weight split of residual {residual:.2f} "
            f"across {n_venues} venues."
        )
    else:
        weights = {v: s / total_score for v, s in scores.items()}
        score_str = ", ".join(f"{v}={scores[v]:.4f}" for v in scores)
        rationale = (
            f"Sharpe-like scores: {score_str}. "
            f"Residual {residual:.2f} distributed proportionally to score "
            f"(floor {floor_per_venue:.2f} per venue)."
        )

    capital = {
        v: floor_per_venue + residual * weights[v] for v in venue_metrics
    }

    log.info(
        "allocator.run",
        bankroll=bankroll_usd,
        venues=list(venue_metrics.keys()),
        capital=capital,
        weights=weights,
    )

    return AllocationResult(
        capital=capital,
        scores=scores,
        weights=weights,
        rationale=rationale,
    )

