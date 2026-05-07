"""Tests for src/sentinel/allocator.py.

[AI-AGENT-CONTRIBUTION] Generated 2026-05-07 by Claude.
See `docs/prompts/2026-05-07_sentinel_allocator.md` for prompt provenance.
"""

from __future__ import annotations

import math

import pytest

from src.sentinel.allocator import (
    LEGS_PER_CYCLE,
    AllocationResult,
    VenueMetrics,
    _venue_score,
    allocate,
)


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------


def make_metrics(
    freq: float = 1.0,
    size: float = 5.0,
    pass_rate: float = 0.8,
    sigma: float = 1.0,
) -> VenueMetrics:
    """Convenience builder. Defaults represent a 'typical' venue."""
    return VenueMetrics(
        freq_per_sec=freq,
        avg_size_bps=size,
        pass_rate=pass_rate,
        pnl_sigma_usd=sigma,
    )


# ---------------------------------------------------------------
# _venue_score: scoring function
# ---------------------------------------------------------------


def test_score_with_positive_inputs() -> None:
    m = VenueMetrics(2.0, 10.0, 0.5, 4.0)
    # raw = 2 * 10 * 0.5 = 10; score = 10 / 4 = 2.5
    assert _venue_score(m) == pytest.approx(2.5)


def test_score_zero_when_sigma_is_zero() -> None:
    assert _venue_score(make_metrics(sigma=0.0)) == 0.0


def test_score_zero_when_sigma_is_negative() -> None:
    assert _venue_score(make_metrics(sigma=-1.0)) == 0.0


def test_score_zero_when_pass_rate_is_zero() -> None:
    assert _venue_score(make_metrics(pass_rate=0.0)) == 0.0


def test_score_zero_when_size_is_negative() -> None:
    """Negative expected size means losing trades on average. Score = 0."""
    assert _venue_score(make_metrics(size=-3.0)) == 0.0


# ---------------------------------------------------------------
# allocate: structural invariants
# ---------------------------------------------------------------


def test_allocate_returns_one_entry_per_venue() -> None:
    result = allocate(
        venue_metrics={
            "binance": make_metrics(),
            "kraken": make_metrics(),
            "coinbase": make_metrics(),
            "bybit": make_metrics(),
        },
        bankroll_usd=10_000.0,
        max_trade_size_usd=100.0,
    )
    assert set(result.capital.keys()) == {"binance", "kraken", "coinbase", "bybit"}


def test_allocated_capital_sums_to_bankroll() -> None:
    """Total dollars out should equal bankroll in (no money created/lost)."""
    result = allocate(
        venue_metrics={
            "binance": make_metrics(freq=2.0, size=8.0),
            "kraken": make_metrics(freq=0.5, size=3.0),
            "coinbase": make_metrics(freq=1.0, size=5.0),
            "bybit": make_metrics(freq=1.5, size=6.0),
        },
        bankroll_usd=10_000.0,
        max_trade_size_usd=100.0,
    )
    assert math.isclose(sum(result.capital.values()), 10_000.0, rel_tol=1e-9)


def test_weights_sum_to_one() -> None:
    result = allocate(
        venue_metrics={
            "a": make_metrics(freq=1.0),
            "b": make_metrics(freq=2.0),
        },
        bankroll_usd=5_000.0,
        max_trade_size_usd=50.0,
    )
    assert math.isclose(sum(result.weights.values()), 1.0, rel_tol=1e-9)


def test_each_venue_gets_at_least_floor() -> None:
    """No venue should ever fall below its operational floor, even if
    its score is the lowest in the set."""
    floor = 100.0 * LEGS_PER_CYCLE
    result = allocate(
        venue_metrics={
            "a": make_metrics(freq=10.0),
            "b": make_metrics(freq=0.001),  # tiny but non-zero
            "c": make_metrics(freq=1.0),
        },
        bankroll_usd=10_000.0,
        max_trade_size_usd=100.0,
    )
    for v, cap in result.capital.items():
        assert cap >= floor - 1e-9, f"{v} got {cap}, below floor {floor}"


# ---------------------------------------------------------------
# allocate: monotonicity
# ---------------------------------------------------------------


def test_higher_score_gets_strictly_more_capital() -> None:
    """A venue with strictly better metrics should receive more capital."""
    result = allocate(
        venue_metrics={
            "good": make_metrics(freq=10.0, size=10.0),
            "bad": make_metrics(freq=1.0, size=1.0),
        },
        bankroll_usd=10_000.0,
        max_trade_size_usd=100.0,
    )
    assert result.capital["good"] > result.capital["bad"]


def test_zero_score_venue_gets_only_floor() -> None:
    """A venue with sigma=0 (zero score) receives only the operational floor."""
    floor = 100.0 * LEGS_PER_CYCLE
    result = allocate(
        venue_metrics={
            "active": make_metrics(freq=2.0),
            "dormant": make_metrics(sigma=0.0),
        },
        bankroll_usd=10_000.0,
        max_trade_size_usd=100.0,
    )
    assert result.capital["dormant"] == pytest.approx(floor)


def test_all_zero_scores_falls_back_to_equal_weights() -> None:
    """When no venue has a positive score, allocator splits residual equally."""
    result = allocate(
        venue_metrics={
            "a": make_metrics(sigma=0.0),
            "b": make_metrics(sigma=0.0),
            "c": make_metrics(sigma=0.0),
        },
        bankroll_usd=3_000.0,
        max_trade_size_usd=100.0,
    )
    # 3 venues × (100 * 3) floor = 900; residual = 2100; equal split = 700
    # each. Total per venue = 300 + 700 = 1000.
    expected_each = 1_000.0
    for v in ("a", "b", "c"):
        assert math.isclose(result.capital[v], expected_each, rel_tol=1e-9)


# ---------------------------------------------------------------
# allocate: input validation
# ---------------------------------------------------------------


def test_empty_venues_raises() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        allocate({}, bankroll_usd=1000.0, max_trade_size_usd=10.0)


def test_negative_bankroll_raises() -> None:
    with pytest.raises(ValueError, match="bankroll_usd"):
        allocate(
            {"a": make_metrics()},
            bankroll_usd=-100.0,
            max_trade_size_usd=10.0,
        )


def test_zero_bankroll_raises() -> None:
    with pytest.raises(ValueError, match="bankroll_usd"):
        allocate(
            {"a": make_metrics()},
            bankroll_usd=0.0,
            max_trade_size_usd=10.0,
        )


def test_negative_max_trade_size_raises() -> None:
    with pytest.raises(ValueError, match="max_trade_size_usd"):
        allocate(
            {"a": make_metrics()},
            bankroll_usd=1000.0,
            max_trade_size_usd=-5.0,
        )


def test_bankroll_too_small_for_floors_raises() -> None:
    # 4 venues × 100 USD × 3 legs = 1200 floor; bankroll 1000 < floor
    with pytest.raises(ValueError, match="too small"):
        allocate(
            venue_metrics={v: make_metrics() for v in ("a", "b", "c", "d")},
            bankroll_usd=1000.0,
            max_trade_size_usd=100.0,
        )


# ---------------------------------------------------------------
# Output type
# ---------------------------------------------------------------


def test_returns_allocation_result_with_rationale() -> None:
    result = allocate(
        venue_metrics={"a": make_metrics()},
        bankroll_usd=1_000.0,
        max_trade_size_usd=50.0,
    )
    assert isinstance(result, AllocationResult)
    assert isinstance(result.rationale, str)
    assert len(result.rationale) > 0
