"""Tests for src/guardian/features.py."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.brain.cycles import Cycle, Edge
from src.guardian.features import (
    FEATURE_ORDER,
    BookSnapshot,
    compute_features,
    feature_vector,
)


def _book(spread_bps: float = 1.0, mid: float = 100.0) -> BookSnapshot:
    half = mid * spread_bps / 20_000.0
    return BookSnapshot(
        venue="binance", symbol="BTC/USDT",
        ts=datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc),
        bid_px=mid - half, bid_sz=10.0,
        ask_px=mid + half, ask_sz=10.0,
        depth5_bids=[(mid - half, 10.0)] * 5,
        depth5_asks=[(mid + half, 10.0)] * 5,
    )


def _cycle() -> Cycle:
    e = Edge("A", "B", rate=1.0, fee=0.0)
    return Cycle(legs=(e, e, e), log_return=0.0)


def test_returns_full_feature_set() -> None:
    feats = compute_features(
        cycle=_cycle(),
        leg_books=[_book(), _book(), _book()],
        history=[_book()] * 30,
        signal_time=datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc),
    )
    for k in FEATURE_ORDER:
        assert k in feats


def test_rejects_wrong_number_of_legs() -> None:
    with pytest.raises(ValueError, match="3 leg books"):
        compute_features(
            cycle=_cycle(),
            leg_books=[_book(), _book()],
            history=[],
            signal_time=datetime.now(timezone.utc),
        )


def test_feature_vector_order_stable() -> None:
    feats = compute_features(
        cycle=_cycle(),
        leg_books=[_book(), _book(), _book()],
        history=[_book()] * 30,
        signal_time=datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc),
    )
    v = feature_vector(feats)
    assert len(v) == len(FEATURE_ORDER)


def test_time_features_in_unit_circle() -> None:
    feats = compute_features(
        cycle=_cycle(),
        leg_books=[_book(), _book(), _book()],
        history=[_book()] * 30,
        signal_time=datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc),
    )
    for k in ("tod_sin", "tod_cos", "dow_sin", "dow_cos"):
        assert -1.0 <= feats[k] <= 1.0
