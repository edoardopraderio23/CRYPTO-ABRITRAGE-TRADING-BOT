"""Labels for the Guardian: replay each cycle at t+50ms and decide
whether the realised fill stayed within the slippage tolerance on
every leg.

Reference: TECHNICAL_PLAN.md §4 (Labeling rule).
Rule: y = 1 ⇔ realised fill within 5 bps of mid-at-signal on all 3 legs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.brain.cycles import Cycle
from src.guardian.features import BookSnapshot

REPLAY_DELAY_MS: int = 50
SLIPPAGE_TOLERANCE_BPS: float = 5.0


@dataclass(frozen=True)
class LabelResult:
    label: int
    per_leg_slippage_bps: list[float]
    max_slippage_bps: float
    insufficient_depth: bool


def compute_label(
    cycle: Cycle,
    leg_books_at_signal: Sequence[BookSnapshot],
    leg_books_at_replay: Sequence[BookSnapshot],
    trade_size_per_leg: float = 1.0,
    tolerance_bps: float = SLIPPAGE_TOLERANCE_BPS,
) -> LabelResult:
    """Walk depth-5 at t+50ms; positive iff every leg fills within tolerance."""
    if len(leg_books_at_signal) != 3 or len(leg_books_at_replay) != 3:
        raise ValueError("Expected 3 leg books each (triangular cycle)")

    per_leg: list[float] = []
    insufficient = False
    for book_sig, book_replay in zip(leg_books_at_signal, leg_books_at_replay):
        fill_px, ok = _walk_depth(book_replay.depth5_asks, trade_size_per_leg)
        if not ok or book_sig.mid == 0:
            insufficient = True
            per_leg.append(float("inf"))
            continue
        slip = abs(fill_px - book_sig.mid) / book_sig.mid * 10_000.0
        per_leg.append(slip)

    all_within = not insufficient and all(s <= tolerance_bps for s in per_leg)
    return LabelResult(
        label=int(all_within),
        per_leg_slippage_bps=per_leg,
        max_slippage_bps=max(per_leg) if per_leg else 0.0,
        insufficient_depth=insufficient,
    )


def _walk_depth(
    ladder: list[tuple[float, float]], size: float,
) -> tuple[float, bool]:
    remaining = size
    total_cost = 0.0
    for px, sz in ladder:
        take = min(remaining, sz)
        total_cost += take * px
        remaining -= take
        if remaining <= 0:
            return total_cost / size, True
    return 0.0, False
