"""Tests for src/sentinel/risk_gate.py."""

from __future__ import annotations

from src.sentinel.inventory import InventoryTracker
from src.sentinel.risk_gate import evaluate_risk


def test_passes_with_clean_state() -> None:
    t = InventoryTracker(cap_usd_per_currency=1000)
    result = evaluate_risk(t, "BTC", 100.0, [1.0] * 20)
    assert result.passed is True
    assert result.rejection_reason is None


def test_rejects_inventory_breach() -> None:
    t = InventoryTracker(cap_usd_per_currency=500)
    t.record_fill("BTC", 400.0)
    result = evaluate_risk(t, "BTC", 200.0, [1.0] * 20)
    assert result.passed is False
    assert result.rejection_reason == "inventory_cap_breach"
    assert result.inventory_breach_currency == "BTC"


def test_rejects_when_drawdown_halted() -> None:
    t = InventoryTracker(cap_usd_per_currency=1000)
    halt_pnls = [1.0] * 29 + [-1000.0]
    result = evaluate_risk(t, "BTC", 50.0, halt_pnls)
    assert result.passed is False
    assert result.rejection_reason == "drawdown_below_tripwire"


def test_inventory_takes_precedence_over_drawdown() -> None:
    """If both would reject, the more specific (inventory) reason is reported."""
    t = InventoryTracker(cap_usd_per_currency=500)
    t.record_fill("BTC", 400.0)
    halt_pnls = [1.0] * 29 + [-1000.0]
    result = evaluate_risk(t, "BTC", 200.0, halt_pnls)
    assert result.rejection_reason == "inventory_cap_breach"
