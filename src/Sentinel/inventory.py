"""Inventory cap tracking: per-currency exposure limit.

Reference: TECHNICAL_PLAN.md §6 (Sentinel)
AGENTS.md §3.3: cap values are LOCKED via config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass
class InventoryTracker:
    """Mutable per-currency exposure tracker. Used by the Risk Gate to
    decide whether a candidate cycle would breach any cap.
    """

    cap_usd_per_currency: float = 1000.0
    base_currency: str = "USDT"
    _exposure_usd: dict[str, float] = field(default_factory=dict)

    def current_exposure(self) -> Mapping[str, float]:
        return dict(self._exposure_usd)

    def record_fill(self, currency: str, delta_usd: float) -> None:
        """Record a leg fill. `delta_usd` is signed: positive when buying
        `currency`, negative when selling. Base currency does not count
        toward inventory (we hold it by definition).
        """
        if currency == self.base_currency:
            return
        self._exposure_usd[currency] = (
            self._exposure_usd.get(currency, 0.0) + delta_usd
        )

    def would_breach(self, currency: str, additional_usd: float) -> bool:
        """Would `additional_usd` of new exposure to `currency` push us
        above the cap?
        """
        if currency == self.base_currency:
            return False
        new = abs(self._exposure_usd.get(currency, 0.0) + additional_usd)
        return new > self.cap_usd_per_currency

    def reset(self) -> None:
        self._exposure_usd.clear()
