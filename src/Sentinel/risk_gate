"""Gate 3 of the Triple-Gate: composes inventory cap + drawdown halt.

A trade fires only if neither check rejects.

Reference: TECHNICAL_PLAN.md §6, AGENTS.md §4
(requires Edoardo + Andrea/Giacomo review).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.sentinel.drawdown import DrawdownResult, evaluate_drawdown
from src.sentinel.inventory import InventoryTracker


@dataclass(frozen=True)
class RiskGateResult:
    passed: bool
    rejection_reason: str | None
    inventory_breach_currency: str | None
    drawdown: DrawdownResult


def evaluate_risk(
    inventory: InventoryTracker,
    additional_currency: str,
    additional_usd: float,
    realised_pnl_window: list[float],
) -> RiskGateResult:
    """Decide pass/fail on inventory + drawdown.

    Inventory is checked first (cheaper, deterministic). Drawdown is
    always computed for the audit trail, even when inventory rejects.
    """
    drawdown = evaluate_drawdown(realised_pnl_window)

    if inventory.would_breach(additional_currency, additional_usd):
        return RiskGateResult(
            passed=False,
            rejection_reason="inventory_cap_breach",
            inventory_breach_currency=additional_currency,
            drawdown=drawdown,
        )

    if drawdown.halted:
        return RiskGateResult(
            passed=False,
            rejection_reason=drawdown.reason,
            inventory_breach_currency=None,
            drawdown=drawdown,
        )

    return RiskGateResult(
        passed=True,
        rejection_reason=None,
        inventory_breach_currency=None,
        drawdown=drawdown,
    )
