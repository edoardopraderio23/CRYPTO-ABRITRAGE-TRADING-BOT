"""Walk-forward backtest replay loop.

Reads book snapshots in time order from the DB, builds a price graph
at each tick, runs Bellman-Ford to detect cycles, applies all three
gates, simulates fills at t+50ms, and emits SimulatedTrade outcomes
to be aggregated by `metrics.compute_metrics`.

This is the integration layer; it owns the orchestration but
delegates the math to Brain / Guardian / Sentinel / fill_model.

Reference: TECHNICAL_PLAN.md §8 (Backtest design).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import structlog

from src.brain.cycles import Edge, detect_negative_cycles
from src.brain.profit_gate import passes as passes_profit
from src.executor.fill_model import simulate_aggressive_fill
from src.executor.metrics import SimulatedTrade
from src.guardian.confidence_gate import ConfidenceGate
from src.guardian.features import BookSnapshot, compute_features

log = structlog.get_logger(__name__)

REPLAY_DELAY_MS: int = 50


@dataclass(frozen=True)
class ReplayConfig:
    start: datetime
    end: datetime
    fee_per_leg: float = 0.001
    slippage_buffer_bps: float = 5.0
    trade_size_usd: float = 100.0
    confidence_model_path: Path | None = None


def replay(
    book_history: Iterable[BookSnapshot],
    config: ReplayConfig,
) -> list[SimulatedTrade]:
    """Replay one historical window end-to-end."""
    history = sorted(book_history, key=lambda b: b.ts)
    if not history:
        return []

    # Load Guardian artefact if provided
    gate: ConfidenceGate | None = None
    if config.confidence_model_path:
        gate = ConfidenceGate(config.confidence_model_path)

    trades: list[SimulatedTrade] = []

    # Group ticks by (venue, symbol) so we can build a graph per venue
    # at each timestamp. v1 just processes by global tick order; more
    # sophisticated grouping is future work.
    for i, book_at_signal in enumerate(history):
        if not (config.start <= book_at_signal.ts <= config.end):
            continue

        edges = _build_edges_for_venue(book_at_signal, history, config.fee_per_leg)
        if len(edges) < 3:
            continue

        cycles = detect_negative_cycles(edges)
        for cycle in cycles:
            # Gate 1: Profit
            pg = passes_profit(cycle, config.slippage_buffer_bps)
            if not pg.passed:
                trades.append(_trade(book_at_signal, cycle, pg, False, False, 0.0, 0.0, False))
                continue

            # Features for Guardian (Gate 2)
            leg_books = _resolve_leg_books(cycle, book_at_signal, history)
            if leg_books is None:
                continue
            feats = compute_features(cycle, leg_books, history[max(0, i - 30):i], book_at_signal.ts)

            if gate is not None:
                cg = gate.evaluate(feats)
                passed_conf = cg.passed
                p_hat = cg.p_hat
            else:
                passed_conf, p_hat = True, 1.0

            if not passed_conf:
                trades.append(_trade(book_at_signal, cycle, pg, passed_conf, False, p_hat, 0.0, False))
                continue

            # Gate 3 (Risk) — wire in from src.sentinel.risk_gate when ready
            passed_risk = True

            # Simulate fills at t + 50ms
            replay_books = _book_after_delay(book_at_signal, history, REPLAY_DELAY_MS)
            realised_bps, failure = _simulate_cycle_fill(
                cycle, leg_books, replay_books, config,
            )

            trades.append(_trade(
                book_at_signal, cycle, pg, passed_conf, passed_risk,
                p_hat, realised_bps, failure,
            ))

    return trades


def _build_edges_for_venue(
    current: BookSnapshot,
    history: list[BookSnapshot],
    fee: float,
) -> list[Edge]:
    # TODO: implement — pull latest quote per (currency_pair) on the same venue,
    # build directed graph of currency conversions.
    return []


def _resolve_leg_books(
    cycle, current: BookSnapshot, history: list[BookSnapshot],
) -> list[BookSnapshot] | None:
    # TODO: for each leg, return the BookSnapshot of the relevant pair
    # at or just before `current.ts`.
    return None


def _book_after_delay(
    current: BookSnapshot, history: list[BookSnapshot], delay_ms: int,
) -> list[BookSnapshot] | None:
    target_ts = current.ts + timedelta(milliseconds=delay_ms)
    # TODO: return the snapshot at or just after target_ts per leg.
    return None


def _simulate_cycle_fill(cycle, sig_books, replay_books, config):
    if replay_books is None:
        return 0.0, True
    total_log = 0.0
    for sig, rep in zip(sig_books, replay_books):
        fill = simulate_aggressive_fill(
            ladder=rep.depth5_asks,
            notional_usd=config.trade_size_usd,
            fee_per_leg=config.fee_per_leg,
            reference_price=sig.mid,
        )
        if not fill.filled:
            return 0.0, True
        total_log += fill.realised_log_return
    return total_log * 10_000.0, False  # convert log to bps


def _trade(book, cycle, pg, conf, risk, p_hat, realised_bps, failure):
    return SimulatedTrade(
        ts_signal_unix=book.ts.timestamp(),
        expected_return_bps=cycle.log_return * 10_000.0,
        realised_return_bps=realised_bps,
        p_hat=p_hat,
        passed_profit_gate=pg.passed,
        passed_confidence_gate=conf,
        passed_risk_gate=risk,
        failure_unwind=failure,
        end_to_end_latency_ms=20.0,  # TODO: read from book snapshot's metadata
    )