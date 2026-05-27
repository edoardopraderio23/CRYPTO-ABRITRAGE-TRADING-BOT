"""Enumerate every candidate triangular cycle per venue per tick.

For each venue, with our 3 trading currencies (USDT, BTC, ETH) and
3 pairs (BTC/USDT, ETH/USDT, ETH/BTC), there are exactly 2 triangles
(forward + reverse). We compute the post-fee log-return for both and
write *every* candidate to `cycles_detected`, tagged with the Profit
Gate verdict (pass/fail).

This is essential for ML training: the Guardian needs to see both
profitable and unprofitable candidates to learn the difference.
The original `detect_negative_cycles` only returned profitable
cycles, which gave the Guardian zero negative examples and (in
efficient markets) zero examples at all.
"""
from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from datetime import datetime, timezone

import structlog

from src.brain.cycles import Cycle, Edge
from src.brain.profit_gate import passes as passes_profit
from src.db.repositories import BookSnapshot, BookSnapshotRepo, CycleRepo

log = structlog.get_logger(__name__)

POLL_SECONDS: float = 2.0

# Approximate venue taker fees. Realistic side; tune per-pair later.
FEE_BY_VENUE: dict[str, float] = {
    "binance":  0.001,    # 0.10%
    "kraken":   0.0026,   # 0.26%
    "coinbase": 0.006,    # 0.60%
    "bybit":    0.001,    # 0.10%
}

REQUIRED_SYMBOLS: tuple[str, ...] = ("BTC/USDT", "ETH/USDT", "ETH/BTC")


def _make_cycle(legs: list[tuple[str, str, float]], fee: float) -> tuple[Cycle, float]:
    """Build a Cycle from (from, to, rate) tuples + venue fee.

    Returns (cycle_with_post_fee_log_return, raw_pre_fee_log_return).
    """
    edges = tuple(
        Edge(from_ccy=f, to_ccy=t, rate=r, fee=fee) for f, t, r in legs
    )
    post_fee = sum(math.log(r * (1.0 - fee)) for _, _, r in legs)
    raw      = sum(math.log(r) for _, _, r in legs)
    return Cycle(legs=edges, log_return=post_fee), raw


def enumerate_triangles_for_venue(
    venue: str,
    books: list[BookSnapshot],
) -> list[tuple[str, Cycle, float]]:
    """Both directions of the USDT-BTC-ETH triangle for one venue.

    Returns list of (direction_label, cycle_post_fee, raw_pre_fee_log_return).
    """
    fee = FEE_BY_VENUE.get(venue, 0.001)
    by_sym = {b.symbol: b for b in books}

    if not all(s in by_sym for s in REQUIRED_SYMBOLS):
        return []

    btc_usdt = by_sym["BTC/USDT"]
    eth_usdt = by_sym["ETH/USDT"]
    eth_btc  = by_sym["ETH/BTC"]

    # Defensive: skip if any quote is missing or invalid.
    for b in (btc_usdt, eth_usdt, eth_btc):
        if b.bid_px is None or b.ask_px is None:
            return []
        if float(b.bid_px) <= 0 or float(b.ask_px) <= 0:
            return []

    out: list[tuple[str, Cycle, float]] = []

    # ---- Direction 1: USDT -> BTC -> ETH -> USDT ----
    legs_fwd = [
        ("USDT", "BTC",  1.0 / float(btc_usdt.ask_px)),
        ("BTC",  "ETH",  1.0 / float(eth_btc.ask_px)),
        ("ETH",  "USDT",       float(eth_usdt.bid_px)),
    ]
    cycle_fwd, raw_fwd = _make_cycle(legs_fwd, fee)
    out.append(("USDT->BTC->ETH->USDT", cycle_fwd, raw_fwd))

    # ---- Direction 2: USDT -> ETH -> BTC -> USDT ----
    legs_rev = [
        ("USDT", "ETH",  1.0 / float(eth_usdt.ask_px)),
        ("ETH",  "BTC",        float(eth_btc.bid_px)),
        ("BTC",  "USDT",       float(btc_usdt.bid_px)),
    ]
    cycle_rev, raw_rev = _make_cycle(legs_rev, fee)
    out.append(("USDT->ETH->BTC->USDT", cycle_rev, raw_rev))

    return out


def emit_once(
    books_repo: BookSnapshotRepo,
    cycles_repo: CycleRepo,
) -> int:
    """One detection pass: enumerate triangles per venue, persist all
    candidates with their Profit Gate verdict. Returns rows written."""
    snapshots = books_repo.fetch_latest_per_venue_symbol()

    # DIAGNOSTIC: always log what we got back from the DB.
    log.info("emitter.fetch", n_snapshots=len(snapshots))

    by_venue: dict[str, list[BookSnapshot]] = defaultdict(list)
    for s in snapshots:
        by_venue[s.venue].append(s)

    # DIAGNOSTIC: log the symbols we have per venue.
    for v, books in by_venue.items():
        log.info(
            "emitter.venue_books",
            venue=v,
            symbols=[b.symbol for b in books],
            n_books=len(books),
        )

    now = datetime.now(timezone.utc)
    written = 0
    for venue, books in by_venue.items():
        triangles = enumerate_triangles_for_venue(venue, books)
        log.info("emitter.triangles", venue=venue, n_triangles=len(triangles))

        for direction, cycle, raw_lr in triangles:
            r = passes_profit(cycle)
            legs_payload = {
                "direction": direction,
                "legs": [
                    {"from": e.from_ccy, "to": e.to_ccy,
                     "rate": float(e.rate), "fee": float(e.fee)}
                    for e in cycle.legs
                ],
            }
            try:
                cycles_repo.insert(
                    ts=now,
                    venue=venue,
                    legs=json.dumps(legs_payload),
                    raw_log_return=raw_lr,
                    expected_return=float(cycle.log_return),
                    passed_profit=r.passed,
                    rejection_reason=r.rejection_reason,
                    features=None,
                )
                written += 1
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "emitter.insert_failed",
                    venue=venue,
                    direction=direction,
                    err=str(exc),
                )
    return written


def main() -> None:
    books_repo = BookSnapshotRepo.from_env()
    cycles_repo = CycleRepo.from_env()
    log.info("emitter.started", poll_seconds=POLL_SECONDS)
    while True:
        try:
            n = emit_once(books_repo, cycles_repo)
            if n:
                log.info("emitter.emitted", count=n)
        except Exception as exc:  # noqa: BLE001
            log.warning("emitter.error", err=str(exc))
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
