"""Tests for src/sentinel/inventory.py."""

from __future__ import annotations

from src.sentinel.inventory import InventoryTracker


def test_starts_empty() -> None:
    t = InventoryTracker()
    assert t.current_exposure() == {}


def test_record_fill_accumulates() -> None:
    t = InventoryTracker(cap_usd_per_currency=1000)
    t.record_fill("BTC", 500.0)
    t.record_fill("BTC", 200.0)
    assert t.current_exposure()["BTC"] == 700.0


def test_base_currency_not_counted() -> None:
    t = InventoryTracker(base_currency="USDT")
    t.record_fill("USDT", 50_000.0)
    assert t.current_exposure() == {}


def test_breach_detected_above_cap() -> None:
    t = InventoryTracker(cap_usd_per_currency=1000)
    t.record_fill("BTC", 800.0)
    assert t.would_breach("BTC", 300.0) is True


def test_no_breach_below_cap() -> None:
    t = InventoryTracker(cap_usd_per_currency=1000)
    t.record_fill("BTC", 400.0)
    assert t.would_breach("BTC", 300.0) is False


def test_breach_uses_absolute_value() -> None:
    """Shorts count the same as longs against the cap."""
    t = InventoryTracker(cap_usd_per_currency=1000)
    t.record_fill("BTC", -800.0)
    assert t.would_breach("BTC", -300.0) is True


def test_reset_clears_state() -> None:
    t = InventoryTracker()
    t.record_fill("BTC", 500.0)
    t.reset()
    assert t.current_exposure() == {}
