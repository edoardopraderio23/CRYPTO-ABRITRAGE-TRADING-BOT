"""Backtest metrics computation.

Produces the metric set tabulated in TECHNICAL_PLAN.md §8:
  - cumulative post-fee P&L (bps)
  - Sharpe ratio (annualised)
  - hit rate
  - precision-at-threshold (for the Guardian)
  - calibration Brier score
  - failure-unwind frequency
  - latency p50 / p95

Pure functions over a list of SimulatedTrade objects so they're
trivially unit-testable without the rest of the pipeline.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Sequence

# Crypto markets trade ~24x365; we report Sharpe per second annualised
# to a year for direct comparison with traditional desks.
SECONDS_PER_YEAR: int = 365 * 24 * 60 * 60


@dataclass(frozen=True)
class SimulatedTrade:
    """One cycle's outcome through the full Triple-Gate + fill sim."""
    ts_signal_unix: float
    expected_return_bps: float
    realised_return_bps: float
    p_hat: float
    passed_profit_gate: bool
    passed_confidence_gate: bool
    passed_risk_gate: bool
    failure_unwind: bool
    end_to_end_latency_ms: float

    @property
    def fired(self) -> bool:
        return (
            self.passed_profit_gate
            and self.passed_confidence_gate
            and self.passed_risk_gate
            and not self.failure_unwind
        )


@dataclass(frozen=True)
class BacktestMetrics:
    n_candidates: int
    n_passed_profit: int
    n_passed_confidence: int
    n_fired: int
    n_winners: int
    n_failure_unwinds: int
    hit_rate: float
    cumulative_pnl_bps: float
    mean_return_bps: float
    std_return_bps: float
    sharpe_annualised: float
    calibration_brier: float
    precision_at_threshold: float
    latency_p50_ms: float
    latency_p95_ms: float


def compute_metrics(trades: Sequence[SimulatedTrade]) -> BacktestMetrics:
    n_candidates = len(trades)
    n_profit = sum(1 for t in trades if t.passed_profit_gate)
    n_confidence = sum(
        1 for t in trades
        if t.passed_profit_gate and t.passed_confidence_gate
    )
    n_failures = sum(1 for t in trades if t.failure_unwind)

    fired = [t for t in trades if t.fired]
    if not fired:
        return BacktestMetrics(
            n_candidates=n_candidates,
            n_passed_profit=n_profit,
            n_passed_confidence=n_confidence,
            n_fired=0, n_winners=0,
            n_failure_unwinds=n_failures,
            hit_rate=0.0, cumulative_pnl_bps=0.0,
            mean_return_bps=0.0, std_return_bps=0.0,
            sharpe_annualised=0.0,
            calibration_brier=0.0,
            precision_at_threshold=0.0,
            latency_p50_ms=_percentile([t.end_to_end_latency_ms for t in trades], 50),
            latency_p95_ms=_percentile([t.end_to_end_latency_ms for t in trades], 95),
        )

    returns = [t.realised_return_bps for t in fired]
    winners = sum(1 for r in returns if r > 0)

    mean = statistics.fmean(returns)
    sd = statistics.pstdev(returns) if len(returns) > 1 else 0.0
    # Per-trade Sharpe; multiply by sqrt(N trades per year) for annualisation
    sharpe = (mean / sd) * math.sqrt(len(returns)) if sd > 0 else 0.0

    brier = statistics.fmean([
        (t.p_hat - (1.0 if t.realised_return_bps > 0 else 0.0)) ** 2
        for t in fired
    ])

    # Precision-at-threshold: of trades the Confidence Gate let through,
    # what fraction actually produced positive return?
    tp = winners
    precision = tp / len(fired)

    return BacktestMetrics(
        n_candidates=n_candidates,
        n_passed_profit=n_profit,
        n_passed_confidence=n_confidence,
        n_fired=len(fired), n_winners=winners,
        n_failure_unwinds=n_failures,
        hit_rate=winners / len(fired),
        cumulative_pnl_bps=sum(returns),
        mean_return_bps=mean, std_return_bps=sd,
        sharpe_annualised=sharpe,
        calibration_brier=brier,
        precision_at_threshold=precision,
        latency_p50_ms=_percentile([t.end_to_end_latency_ms for t in trades], 50),
        latency_p95_ms=_percentile([t.end_to_end_latency_ms for t in trades], 95),
    )


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * (p / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)