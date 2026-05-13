"""Typed repositories over the four core tables.

Each repository wraps psycopg2 calls in plain Python methods so that
callers (Scout, Brain, Guardian, Sentinel) don't write SQL inline.

DESTINATION: src/db/repositories.py

References:
    - src/db/schema.sql (the schema these wrap)
    - TECHNICAL_PLAN.md §9
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg2
import psycopg2.extras


@dataclass(frozen=True)
class CycleRecord:
    """Row from cycles_detected, returned by CycleRepo.fetch_recent."""
    id: int
    ts: datetime
    venue: str
    legs: list[dict[str, Any]]
    raw_log_return: Decimal
    expected_return: Decimal
    passed_profit: bool


# ---------------------------------------------------------------
# book_snapshots
# ---------------------------------------------------------------


class BookSnapshotRepo:
    """book_snapshots: raw L2 ticks from the Scout."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @classmethod
    def from_env(cls) -> "BookSnapshotRepo":
        return cls(os.environ["DATABASE_URL"])

    def insert(
        self,
        *,
        venue: str,
        symbol: str,
        ts: datetime,
        bid_px: Decimal | None,
        bid_sz: Decimal | None,
        ask_px: Decimal | None,
        ask_sz: Decimal | None,
        depth5_bids: list,
        depth5_asks: list,
    ) -> None:
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO book_snapshots
                  (venue, symbol, ts, bid_px, bid_sz, ask_px, ask_sz,
                   depth5_bids, depth5_asks)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                """,
                (
                    venue, symbol, ts,
                    bid_px, bid_sz, ask_px, ask_sz,
                    json.dumps(depth5_bids), json.dumps(depth5_asks),
                ),
            )


# ---------------------------------------------------------------
# cycles_detected
# ---------------------------------------------------------------


class CycleRepo:
    """cycles_detected: every triangular cycle the Brain emits."""

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
        legs: list[dict[str, Any]],
        raw_log_return: Decimal,
        expected_return: Decimal,
        passed_profit: bool,
        rejection_reason: str | None,
        features: dict[str, Any] | None,
    ) -> int:
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cycles_detected
                  (ts, venue, legs, raw_log_return, expected_return,
                   passed_profit, rejection_reason, features)
                VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    ts, venue, json.dumps(legs),
                    raw_log_return, expected_return,
                    passed_profit, rejection_reason,
                    json.dumps(features) if features else None,
                ),
            )
            row = cur.fetchone()
            assert row is not None
            return int(row[0])

    def fetch_recent(self, *, limit: int = 1000) -> list[CycleRecord]:
        with psycopg2.connect(self.dsn) as conn, conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                "SELECT * FROM cycles_detected ORDER BY ts DESC LIMIT %s",
                (limit,),
            )
            return [
                CycleRecord(
                    id=r["id"],
                    ts=r["ts"],
                    venue=r["venue"],
                    legs=r["legs"],
                    raw_log_return=r["raw_log_return"],
                    expected_return=r["expected_return"],
                    passed_profit=r["passed_profit"],
                )
                for r in cur.fetchall()
            ]


# ---------------------------------------------------------------
# trades_simulated
# ---------------------------------------------------------------


class TradeRepo:
    """trades_simulated: outcome of each candidate after all gates."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @classmethod
    def from_env(cls) -> "TradeRepo":
        return cls(os.environ["DATABASE_URL"])

    def insert(
        self,
        *,
        cycle_id: int,
        ts_signal: datetime,
        ts_filled: datetime | None,
        p_hat: Decimal,
        passed_confidence: bool,
        passed_risk: bool,
        expected_return: Decimal,
        realized_return: Decimal | None,
        failure_unwind: bool,
        model_version: str,
    ) -> None:
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trades_simulated
                  (cycle_id, ts_signal, ts_filled, p_hat,
                   passed_confidence, passed_risk,
                   expected_return, realized_return,
                   failure_unwind, model_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    cycle_id, ts_signal, ts_filled, p_hat,
                    passed_confidence, passed_risk,
                    expected_return, realized_return,
                    failure_unwind, model_version,
                ),
            )


# ---------------------------------------------------------------
# model_versions
# ---------------------------------------------------------------


class ModelVersionRepo:
    """model_versions: full lineage of every trained Guardian model."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @classmethod
    def from_env(cls) -> "ModelVersionRepo":
        return cls(os.environ["DATABASE_URL"])

    def insert(
        self,
        *,
        version: str,
        trained_at: datetime,
        algo: str,
        feature_set: list[str],
        hyperparams: dict[str, Any],
        train_window_start: datetime,
        train_window_end: datetime,
        val_auc: Decimal | None,
        val_precision_at_threshold: Decimal | None,
        decision_threshold: Decimal,
        artifact_path: str,
        notes: str | None,
    ) -> None:
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_versions
                  (version, trained_at, algo, feature_set, hyperparams,
                   train_window_start, train_window_end,
                   val_auc, val_precision_at_threshold,
                   decision_threshold, artifact_path, notes)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version, trained_at, algo,
                    json.dumps(feature_set), json.dumps(hyperparams),
                    train_window_start, train_window_end,
                    val_auc, val_precision_at_threshold,
                    decision_threshold, artifact_path, notes,
                ),
            )
