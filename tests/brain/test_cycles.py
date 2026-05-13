"""Tests for src/brain/cycles.py.

We test invariants property-style where possible — the math is too
easy to get wrong with hand-picked examples alone.

DESTINATION: tests/brain/test_cycles.py
"""

from __future__ import annotations

import math

import pytest

from src.brain.cycles import (
    CYCLE_LENGTH,
    Cycle,
    Edge,
    detect_negative_cycles,
)


# ---------------------------------------------------------------
# Edge weight
# ---------------------------------------------------------------


def test_edge_weight_zero_fee() -> None:
    """w = -ln(rate)."""
    e = Edge("A", "B", rate=2.0, fee=0.0)
    assert e.weight() == pytest.approx(-math.log(2.0))


def test_edge_weight_with_fee() -> None:
    """w = -ln(rate × (1 - fee))."""
    e = Edge("A", "B", rate=1.0, fee=0.001)
    assert e.weight() == pytest.approx(-math.log(1.0 * 0.999))


# ---------------------------------------------------------------
# detect_negative_cycles
# ---------------------------------------------------------------


def test_no_edges_yields_no_cycles() -> None:
    assert detect_negative_cycles([]) == []


def test_no_negative_cycle_when_market_efficient() -> None:
    """If rate(A→B) × rate(B→C) × rate(C→A) == 1, no profit."""
    edges = [
        Edge("USDT", "BTC", rate=1 / 60000.0, fee=0.0),
        Edge("BTC",  "ETH", rate=1 / 0.05,    fee=0.0),
        Edge("ETH",  "USDT", rate=3000.0,     fee=0.0),
    ]
    # Product: (1/60000) * (1/0.05) * 3000 = 1.0 exactly
    assert detect_negative_cycles(edges) == []


def test_detects_profitable_triangle() -> None:
    """rate product > 1 (zero fees) ⇒ should return a cycle."""
    edges = [
        Edge("USDT", "BTC", rate=1 / 60000.0, fee=0.0),
        Edge("BTC",  "ETH", rate=1 / 0.05,    fee=0.0),
        Edge("ETH",  "USDT", rate=3060.0,     fee=0.0),  # 2% richer
    ]
    cycles = detect_negative_cycles(edges)
    assert len(cycles) >= 1
    assert all(isinstance(c, Cycle) for c in cycles)
    assert all(len(c.legs) == CYCLE_LENGTH for c in cycles)


def test_fees_can_kill_a_marginal_cycle() -> None:
    """A 1% raw edge is wiped out by 0.5% per-leg fees."""
    edges = [
        Edge("USDT", "BTC", rate=1 / 60000.0, fee=0.005),
        Edge("BTC",  "ETH", rate=1 / 0.05,    fee=0.005),
        Edge("ETH",  "USDT", rate=3030.0,     fee=0.005),  # 1% raw edge
    ]
    cycles = detect_negative_cycles(edges)
    # With these fees the net log_return should be negative
    for c in cycles:
        assert c.log_return < 0.0


def test_log_return_consistency() -> None:
    """log_return of a returned cycle equals the sum of ln(rate(1-fee))
    over its three legs."""
    edges = [
        Edge("USDT", "BTC", rate=1 / 60000.0, fee=0.001),
        Edge("BTC",  "ETH", rate=1 / 0.05,    fee=0.001),
        Edge("ETH",  "USDT", rate=3100.0,     fee=0.001),
    ]
    cycles = detect_negative_cycles(edges)
    for c in cycles:
        expected = sum(math.log(e.rate * (1 - e.fee)) for e in c.legs)
        assert c.log_return == pytest.approx(expected)


def test_only_triangular_cycles_returned() -> None:
    """v1 emits only 3-leg cycles even if longer ones exist in graph."""
    edges = [
        Edge("USDT", "BTC", rate=1 / 60000.0, fee=0.0),
        Edge("BTC",  "ETH", rate=1 / 0.05,    fee=0.0),
        Edge("ETH",  "DAI", rate=3000.0,      fee=0.0),
        Edge("DAI",  "USDT", rate=1.05,       fee=0.0),  # 4-cycle profit
    ]
    cycles = detect_negative_cycles(edges)
    for c in cycles:
        assert len(c.legs) == CYCLE_LENGTH


def test_duplicate_cycles_deduplicated() -> None:
    """Rotations of the same triangle should not appear twice."""
    edges = [
        Edge("USDT", "BTC", rate=1 / 60000.0, fee=0.0),
        Edge("BTC",  "ETH", rate=1 / 0.05,    fee=0.0),
        Edge("ETH",  "USDT", rate=3100.0,     fee=0.0),
    ]
    cycles = detect_negative_cycles(edges)
    # At most one canonical triangle on this 3-node graph.
    assert len(cycles) <= 1
