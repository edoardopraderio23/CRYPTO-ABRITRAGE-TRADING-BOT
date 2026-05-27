"""Feature engineering for the Guardian (ML scorer).

Computes a fixed-shape feature vector for each candidate cycle so
LightGBM and Random Forest can score it.

Reference: TECHNICAL_PLAN.md §4 (Labeling rule and features).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from src.brain.cycles import Cycle


@dataclass(frozen=True)
class BookSnapshot:
    """Top-of-book + depth-5 at one moment, for one (venue, symbol)."""
    venue: str
    symbol: str
    ts: datetime
    bid_px: float
    bid_sz: float
    ask_px: float
    ask_sz: float
    depth5_bids: list[tuple[float, float]]
    depth5_asks: list[tuple[float, float]]

    @property
    def mid(self) -> float:
        return 0.5 * (self.bid_px + self.ask_px)

    @property
    def spread_bps(self) -> float:
        return (self.ask_px - self.bid_px) / self.mid * 10_000.0 if self.mid else 0.0


def compute_features(
    cycle: Cycle,
    leg_books: Sequence[BookSnapshot],
    history: Sequence[BookSnapshot],
    signal_time: datetime,
) -> dict[str, float]:
    """Feature vector for one cycle at signal time."""
    if len(leg_books) != 3:
        raise ValueError(f"Expected 3 leg books, got {len(leg_books)}")

    features: dict[str, float] = {}
    for i, book in enumerate(leg_books, start=1):
        features[f"spread_bps_leg_{i}"] = book.spread_bps
        features[f"depth5_log_imbalance_leg_{i}"] = _depth5_log_imbalance(book)
        features[f"top_bid_size_leg_{i}"] = book.bid_sz
        features[f"top_ask_size_leg_{i}"] = book.ask_sz

    features["cycle_log_return_bps"] = cycle.log_return * 10_000.0
    spreads = [b.spread_bps for b in leg_books]
    features["mean_spread_bps"] = sum(spreads) / 3.0
    features["max_spread_bps"] = max(spreads)

    features["mean_mid_vol_5s"] = _realised_vol(history, signal_time, 5.0)
    features["mean_mid_vol_30s"] = _realised_vol(history, signal_time, 30.0)
    features.update(_time_features(signal_time))
    return features


def _depth5_log_imbalance(book: BookSnapshot) -> float:
    bid_total = sum(sz for _, sz in book.depth5_bids) or 1e-12
    ask_total = sum(sz for _, sz in book.depth5_asks) or 1e-12
    return math.log(bid_total / ask_total)


def _realised_vol(history, signal_time, window_s):
    cutoff = signal_time.timestamp() - window_s
    window = [b for b in history if b.ts.timestamp() >= cutoff]
    if len(window) < 2:
        return 0.0
    mids = [b.mid for b in window]
    rets = [math.log(mids[i] / mids[i - 1]) for i in range(1, len(mids))]
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var)


def _time_features(ts: datetime) -> dict[str, float]:
    seconds = ts.hour * 3600 + ts.minute * 60 + ts.second
    tod = 2 * math.pi * seconds / 86400.0
    dow = 2 * math.pi * ts.weekday() / 7.0
    return {
        "tod_sin": math.sin(tod), "tod_cos": math.cos(tod),
        "dow_sin": math.sin(dow), "dow_cos": math.cos(dow),
    }


FEATURE_ORDER: tuple[str, ...] = (
    "spread_bps_leg_1", "spread_bps_leg_2", "spread_bps_leg_3",
    "depth5_log_imbalance_leg_1", "depth5_log_imbalance_leg_2",
    "depth5_log_imbalance_leg_3",
    "top_bid_size_leg_1", "top_bid_size_leg_2", "top_bid_size_leg_3",
    "top_ask_size_leg_1", "top_ask_size_leg_2", "top_ask_size_leg_3",
    "cycle_log_return_bps", "mean_spread_bps", "max_spread_bps",
    "mean_mid_vol_5s", "mean_mid_vol_30s",
    "tod_sin", "tod_cos", "dow_sin", "dow_cos",
)


def feature_vector(features: dict[str, float]) -> list[float]:
    return [features[k] for k in FEATURE_ORDER]
