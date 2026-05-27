"""Unified L2 order-book streamer for all 4 exchange venues.

Subscribes via CCXT Pro WebSocket, persists each tick to the
`book_snapshots` table via the BookSnapshotRepo.

This module covers two issues simultaneously:
  - Issue #2 (feat(scout): unify L2 streaming for all 4 venues)
  - Issue #1 (feat(scout): integrate Bybit via CCXT Pro)

CCXT Pro abstracts each exchange's WebSocket API behind a uniform
`watch_order_book(symbol)` coroutine. We just dispatch on venue name.

DESTINATION: src/scout/streamer.py

References:
    - TECHNICAL_PLAN.md §1 (latency budget)
    - TECHNICAL_PLAN.md §9 (schema)
    - Issue #1 (Bybit decision)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

import ccxt.pro
import structlog

from src.db.repositories import BookSnapshotRepo

log = structlog.get_logger(__name__)

# Order matters only for logging; venues stream concurrently.
SUPPORTED_VENUES: tuple[str, ...] = ("binance", "kraken", "coinbase", "bybit")

# Each exchange accepts a different set of order-book depth values.
#   Kraken accepts: 10, 25, 100, 500, 1000
#   Bybit  accepts: 1, 50, 200, 1000  (spot markets)
#   Binance / Coinbase are flexible.
# We request more than 5 then slice to depth-5 in _persist().
DEPTH_LIMIT_BY_VENUE: dict[str, int] = {
    "binance":  10,
    "kraken":   10,
    "coinbase": 10,
    "bybit":    50,
}


class Streamer:
    """Stream L2 depth-5 books for one venue, write each tick to Postgres."""

    def __init__(
        self,
        venue: str,
        symbols: Sequence[str],
        repo: BookSnapshotRepo,
        backoff_seconds: float = 1.0,
    ) -> None:
        if venue not in SUPPORTED_VENUES:
            raise ValueError(
                f"Unsupported venue: {venue!r}. "
                f"Supported: {SUPPORTED_VENUES}"
            )
        self.venue = venue
        self.symbols = list(symbols)
        self.repo = repo
        self.backoff = backoff_seconds
        # CCXT Pro auto-selects the right WS client for the venue name.
        self.client = getattr(ccxt.pro, venue)()

    async def close(self) -> None:
        await self.client.close()

    async def run(self) -> None:
        """Subscribe to every symbol concurrently. Restarts on failure."""
        tasks = [self._stream_symbol(s) for s in self.symbols]
        await asyncio.gather(*tasks)

    async def _stream_symbol(self, symbol: str) -> None:
        log.info("scout.subscribe", venue=self.venue, symbol=symbol)
        depth_limit = DEPTH_LIMIT_BY_VENUE.get(self.venue, 10)
        while True:
            try:
                book = await self.client.watch_order_book(symbol, limit=depth_limit)
                await self._persist(symbol, book)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — top-level resilience
                log.warning(
                    "scout.stream_error",
                    venue=self.venue,
                    symbol=symbol,
                    err=str(exc),
                )
                await asyncio.sleep(self.backoff)

    async def _persist(self, symbol: str, book: dict) -> None:
        bid_px, bid_sz = (book["bids"][0] if book["bids"] else (None, None))
        ask_px, ask_sz = (book["asks"][0] if book["asks"] else (None, None))

        # psycopg2 is sync; offload to a worker thread so the WS loop
        # is never blocked on database I/O.
        await asyncio.to_thread(
            self.repo.insert,
            venue=self.venue,
            symbol=symbol,
            ts=datetime.now(timezone.utc),
            bid_px=_dec(bid_px),
            bid_sz=_dec(bid_sz),
            ask_px=_dec(ask_px),
            ask_sz=_dec(ask_sz),
            depth5_bids=book["bids"][:5],
            depth5_asks=book["asks"][:5],
        )


def _dec(v: float | None) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


async def run_all_venues(
    symbols: Sequence[str],
    repo: BookSnapshotRepo,
) -> None:
    """Run streamers for every supported venue concurrently."""
    streamers = [Streamer(v, symbols, repo) for v in SUPPORTED_VENUES]
    try:
        await asyncio.gather(*(s.run() for s in streamers))
    finally:
        await asyncio.gather(*(s.close() for s in streamers))


if __name__ == "__main__":
    # Continuous run: streams all 4 venues forever until the process is killed.
    async def main() -> None:
        repo = BookSnapshotRepo.from_env()
        await run_all_venues(
            symbols=("BTC/USDT", "ETH/USDT", "ETH/BTC"),
            repo=repo,
        )

    asyncio.run(main())
