"""Tests for src/sentinel/drawdown.py."""

from __future__ import annotations

from src.sentinel.drawdown import (
    DEFAULT_SIGMA_MULTIPLIER,
    MIN_SAMPLES_FOR_HALT,
    evaluate_drawdown,
)


def test_insufficient_data_does_not_halt() -> None:
    result = evaluate_drawdown([1.0, 2.0, 3.0])
    assert result.halted is False


def test_halts_when_pnl_far_below_tripwire() -> None:
    # 29 small positives + 1 big loss creates very negative rolling P&L
    pnls = [1.0] * 29 + [-1000.0]
    assert len(pnls) >= MIN_SAMPLES_FOR_HALT
    result = evaluate_drawdown(pnls)
    assert result.halted is True
    assert result.reason == "drawdown_below_tripwire"


def test_no_halt_for_constant_positive_returns() -> None:
    """Constant series → sigma = 0 → tripwire = mu; total >> mu."""
    pnls = [1.0] * 30
    result = evaluate_drawdown(pnls)
    assert result.halted is False


def test_reports_mu_and_sigma() -> None:
    pnls = [1.0, 2.0, 3.0] * 10
    result = evaluate_drawdown(pnls)
    assert result.mu_usd == 2.0
    assert result.sigma_usd > 0.0
