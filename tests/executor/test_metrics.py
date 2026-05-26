"""Tests for src/executor/metrics.py."""

from __future__ import annotations

import math

import pytest

from src.executor.metrics import (
    BacktestMetrics,
    SimulatedTrade,
    compute_metrics,
)


def _trade(
    expected_bps: float = 10.0,
    realised_bps: float = 8.0,
    p_hat: float = 0.9,
    passed_profit: bool = True,
    passed_confidence: bool = True,
    passed_risk: bool = True,
    failure: bool = False,
    latency: float = 20.0,
) -> SimulatedTrade:
    return SimulatedTrade(
        ts_signal_unix=0.0,
        expected_return_bps=expected_bps,
        realised_return_bps=realised_bps,
        p_hat=p_hat,
        passed_profit_gate=passed_profit,
        passed_confidence_gate=passed_confidence,
        passed_risk_gate=passed_risk,
        failure_unwind=failure,
        end_to_end_latency_ms=latency,
    )


def test_no_trades_returns_zero_metrics() -> None:
    result = compute_metrics([])
    assert result.n_fired == 0
    assert result.hit_rate == 0.0
    assert result.cumulative_pnl_bps == 0.0


def test_fired_only_when_all_gates_pass_and_no_failure() -> None:
    trades = [
        _trade(),                                       # fires
        _trade(passed_confidence=False),                # rejected at Gate 2
        _trade(passed_risk=False),                      # rejected at Gate 3
        _trade(failure=True),                           # failure_unwind
    ]
    m = compute_metrics(trades)
    assert m.n_fired == 1


def test_hit_rate_and_pnl_aggregation() -> None:
    trades = [
        _trade(realised_bps=10.0),
        _trade(realised_bps=-5.0),
        _trade(realised_bps=20.0),
        _trade(realised_bps=-10.0),
    ]
    m = compute_metrics(trades)
    assert m.n_fired == 4
    assert m.n_winners == 2
    assert m.hit_rate == 0.5
    assert m.cumulative_pnl_bps == pytest.approx(15.0)


def test_brier_perfect_calibration_gives_zero() -> None:
    """p_hat=1.0 on every winner, p_hat=0.0 on every loser → Brier 0."""
    trades = [
        _trade(realised_bps=5.0, p_hat=1.0),
        _trade(realised_bps=-5.0, p_hat=0.0),
    ]
    m = compute_metrics(trades)
    assert m.calibration_brier == pytest.approx(0.0)


def test_latency_percentiles() -> None:
    trades = [_trade(latency=l) for l in [10, 12, 15, 20, 25, 30, 40, 50, 60, 100]]
    m = compute_metrics(trades)
    assert 20 <= m.latency_p50_ms <= 30
    assert m.latency_p95_ms >= 50