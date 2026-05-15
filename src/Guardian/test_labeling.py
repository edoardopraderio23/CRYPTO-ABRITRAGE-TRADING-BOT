"""Tests for src/guardian/labeling.py."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.brain.cycles import Cycle, Edge
from src.guardian.features import BookSnapshot
from src.guardian.labeling import compute_label


def _book(ask_px: float = 100.0, ask_sz: float = 10.0) -> BookSnapshot:
    return BookSnapshot(
        venue="binance", symbol="BTC/USDT",
        ts=datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc),
        bid_px=ask_px * 0.9999, bid_sz=10.0,
        ask_px=ask_px, ask_sz=ask_sz,
        depth5_bids=[(ask_px * 0.9999, 10.0)] * 5,
        depth5_asks=[(ask_px, ask_sz)] * 5,
    )


def _cycle() -> Cycle:
    e = Edge("A", "B", rate=1.0, fee=0.001)
    return Cycle(legs=(e, e, e), log_return=0.0)


def test_label_one_when_fill_matches_mid() -> None:
    book = _book(ask_px=100.0)
    result = compute_label(
        cycle=_cycle(),
        leg_books_at_signal=[book, book, book],
        leg_books_at_replay=[book, book, book],
    )
    assert result.label == 1


def test_label_zero_when_price_moves_far_against() -> None:
    sig_book = _book(ask_px=100.0)
    bad_book = _book(ask_px=101.0)  # ~100 bps adverse move
    result = compute_label(
        cycle=_cycle(),
        leg_books_at_signal=[sig_book, sig_book, sig_book],
        leg_books_at_replay=[bad_book, bad_book, bad_book],
    )
    assert result.label == 0
    assert result.max_slippage_bps > 5.0


def test_insufficient_depth_yields_zero_label() -> None:
    sig = _book()
    empty = BookSnapshot(
        venue="binance", symbol="BTC/USDT",
        ts=sig.ts, bid_px=99.0, bid_sz=0.0,
        ask_px=100.0, ask_sz=0.0,
        depth5_bids=[], depth5_asks=[],
    )
    result = compute_label(
        cycle=_cycle(),
        leg_books_at_signal=[sig, sig, sig],
        leg_books_at_replay=[empty, empty, empty],
    )
    assert result.label == 0
    assert result.insufficient_depth is True


def test_rejects_wrong_number_of_legs() -> None:
    with pytest.raises(ValueError, match="3 leg books"):
        compute_label(
            cycle=_cycle(),
            leg_books_at_signal=[_book(), _book()],
            leg_books_at_replay=[_book(), _book()],
        )
