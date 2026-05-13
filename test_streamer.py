"""Tests for src/scout/streamer.py.

These exercise the venue dispatch and validation logic without
hitting real exchange APIs.

DESTINATION: tests/scout/test_streamer.py
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.scout.streamer import SUPPORTED_VENUES, Streamer


def test_supported_venues_includes_bybit() -> None:
    """Bybit must be in the venue list per the issue #1 decision."""
    assert "bybit" in SUPPORTED_VENUES
    assert len(SUPPORTED_VENUES) == 4


def test_rejects_unsupported_venue() -> None:
    repo = MagicMock()
    with pytest.raises(ValueError, match="Unsupported venue"):
        Streamer(
            venue="ftx",  # not a real venue
            symbols=("BTC/USDT",),
            repo=repo,
        )


@pytest.mark.parametrize("venue", SUPPORTED_VENUES)
def test_constructs_for_each_supported_venue(venue: str) -> None:
    """All 4 supported venues must construct without error."""
    repo = MagicMock()
    s = Streamer(venue=venue, symbols=("BTC/USDT",), repo=repo)
    assert s.venue == venue
