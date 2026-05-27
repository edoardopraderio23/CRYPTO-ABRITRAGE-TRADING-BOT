"""Repository pattern for Postgres tables.

Each class owns one table and exposes typed insert/fetch methods.
All connection management is per-call; for high-throughput use we can
add a pool later.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

import psycopg2


# ============================================================
# BookSnapshotRepo  (Scout writes here)
# ============================================================

@dataclass(frozen=True)
class BookSnapshot:
    """Top-of-book + depth-5 at one moment for one (venue, symbol)."""
    venue: str
    symbol: str
    ts: datetime
    bid_px: float
    bid_sz: float
    ask_px: float
    ask_sz: float
    depth5_bids: list
    depth5_asks: list


class BookSnapshotRepo:
    """book_snapshots: order-book ticks from the Scout streamer."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @classmethod
    def from_env(cls) -> "BookSnapshotRepo":
        return cls(os.environ["DATABASE_URL"])

    def insert(
        self,
        *,
        ts: datetime,
        venue: str,
        symbol: str,
        bid_px: float,
        bid_sz: float,
        ask_px: float,
        ask_sz: float,
        depth5_bids: Optional[list] = None,
        depth5_asks: Optional[list] = None,
    ) -> None:
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO book_snapshots
                  (ts, venue, symbol, bid_px, bid_sz, ask_px, ask_sz,
                   depth5_bids, depth5_asks)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    ts, venue, symbol,
                    bid_px, bid_sz, ask_px, ask_sz,
                    json.dumps(depth5_bids) if depth5_bids else None,
                    json.dumps(depth5_asks) if depth5_asks else None,
                ),
            )

    def fetch_latest_per_venue_symbol(self) -> list[BookSnapshot]:
        """Most recent snapshot per (venue, symbol). Used by cycle_emitter."""
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (venue, symbol)
                  venue, symbol, ts,
                  bid_px, bid_sz, ask_px, ask_sz,
                  depth5_bids, depth5_asks
                FROM book_snapshots
                ORDER BY venue, symbol, ts DESC
                """
            )
            rows = cur.fetchall()
        return [
            BookSnapshot(
                venue=r[0], symbol=r[1], ts=r[2],
                bid_px=float(r[3]), bid_sz=float(r[4]),
                ask_px=float(r[5]), ask_sz=float(r[6]),
                depth5_bids=r[7] or [],
                depth5_asks=r[8] or [],
            )
            for r in rows
        ]


# ============================================================
# CycleRepo  (Brain / cycle_emitter writes here)
# ============================================================

class CycleRepo:
    """cycles_detected: triangular cycles emitted by the Brain."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @classmethod
    def from_env(cls) -> "CycleRepo":
        return cls(os.environ["DATABASE_URL"])

    def insert(
        self,
        *,
        ts: datetime,
        venue: str,
        legs: str,                       # JSON string -> stored as jsonb
        raw_log_return: float,           # pre-fee log return
        expected_return: float,          # post-fee log return
        passed_profit: bool,
        rejection_reason: Optional[str] = None,
        features: Optional[str] = None,  # optional JSON string -> jsonb
    ) -> None:
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cycles_detected
                  (ts, venue, legs, raw_log_return, expected_return,
                   passed_profit, rejection_reason, features)
                VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
                """,
                (ts, venue, legs, raw_log_return, expected_return,
                 passed_profit, rejection_reason, features),
            )


# ============================================================
# ModelVersionRepo  (Guardian training writes here)
# ============================================================

class ModelVersionRepo:
    """model_versions: trained Guardian metadata for reproducibility."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @classmethod
    def from_env(cls) -> "ModelVersionRepo":
        return cls(os.environ["DATABASE_URL"])

    def insert(
        self,
        *,
        model_name: str,
        train_start: Optional[datetime] = None,
        train_end: Optional[datetime] = None,
        val_end: Optional[datetime] = None,
        threshold: Optional[float] = None,
        precision_val: Optional[float] = None,
        recall_val: Optional[float] = None,
        bundle_path: Optional[str] = None,
    ) -> int:
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_versions
                  (model_name, train_start, train_end, val_end,
                   threshold, precision_val, recall_val, bundle_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (model_name, train_start, train_end, val_end,
                 threshold, precision_val, recall_val, bundle_path),
            )
            return cur.fetchone()[0]


# ============================================================
# TradeRepo  (Backtest / Executor writes here)
# ============================================================

class TradeRepo:
    """trades_simulated: backtest output."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @classmethod
    def from_env(cls) -> "TradeRepo":
        return cls(os.environ["DATABASE_URL"])

    def insert(
        self,
        *,
        simulated_at: datetime,
        cycle_id: Optional[int] = None,
        model_version_id: Optional[int] = None,
        gross_pnl_usd: Optional[float] = None,
        net_pnl_usd: Optional[float] = None,
        trade_size_usd: Optional[float] = None,
        fees_paid_usd: Optional[float] = None,
        slippage_bps: Optional[float] = None,
        passed_all_gates: bool = True,
        notes: Optional[str] = None,
    ) -> None:
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trades_simulated
                  (simulated_at, cycle_id, model_version_id,
                   gross_pnl_usd, net_pnl_usd, trade_size_usd,
                   fees_paid_usd, slippage_bps, passed_all_gates, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (simulated_at, cycle_id, model_version_id,
                 gross_pnl_usd, net_pnl_usd, trade_size_usd,
                 fees_paid_usd, slippage_bps, passed_all_gates, notes),
            )


# ============================================================
# CapitalAllocationRepo  (Sentinel allocator writes here)
# ============================================================

class CapitalAllocationRepo:
    """capital_allocations: daily allocator decisions."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @classmethod
    def from_env(cls) -> "CapitalAllocationRepo":
        return cls(os.environ["DATABASE_URL"])

    def insert(
        self,
        *,
        bankroll_usd: Decimal,
        venue: str,
        allocated_usd: Decimal,
        score: Decimal,
        weight: Decimal,
        rationale: Optional[str] = None,
    ) -> None:
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO capital_allocations
                  (bankroll_usd, venue, allocated_usd, score, weight, rationale)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (bankroll_usd, venue, allocated_usd, score, weight, rationale),
            )
