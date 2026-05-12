"""Bellman-Ford negative-cycle detection on a venue's price graph.

For each detected cycle, we compute the post-fee log-return so the
Profit Gate (separate module) can decide whether to keep it.

DESTINATION: src/brain/cycles.py

References:
    - TECHNICAL_PLAN.md §3 (Profit Gate spec)
    - TECHNICAL_PLAN.md §7 (Triple-Gate diagram)
    - Edge weight: w(i → j) = -ln(rate(i,j) × (1 - fee))
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)

# We only emit cycles of exactly this length. Triangular arbitrage by
# definition uses three legs; longer cycles are out of scope for v1.
CYCLE_LENGTH: int = 3


@dataclass(frozen=True)
class Edge:
    """One directed leg in the price graph: 1 unit of from_ccy buys
    `rate` units of to_ccy, less the venue taker fee.
    """
    from_ccy: str
    to_ccy: str
    rate: float
    fee: float       # taker fee, in [0, 1)

    def weight(self) -> float:
        """w = -ln(rate × (1 - fee)). Negative iff this leg is profitable."""
        return -math.log(self.rate * (1.0 - self.fee))


@dataclass(frozen=True)
class Cycle:
    """A triangular cycle: list of three edges that close back to the
    starting currency, with the realised post-fee log-return.
    """
    legs: tuple[Edge, Edge, Edge]
    log_return: float


def detect_negative_cycles(edges: list[Edge]) -> list[Cycle]:
    """Find all length-3 negative cycles in the price graph.

    Uses Bellman-Ford with a sentinel source: we add a virtual node
    with zero-weight edges to every other node, so any negative cycle
    in the original graph is reachable. After |V| iterations, any
    edge that can still be relaxed lies on a negative cycle.

    Returns the cycles in arbitrary order. The caller (Profit Gate)
    filters them.
    """
    if not edges:
        return []

    nodes = sorted({e.from_ccy for e in edges} | {e.to_ccy for e in edges})

    # Source-free trick: distances start at 0 everywhere.
    dist: dict[str, float] = {n: 0.0 for n in nodes}
    pred: dict[str, Edge | None] = {n: None for n in nodes}

    # Relax |V| - 1 times.
    for _ in range(len(nodes) - 1):
        updated = False
        for e in edges:
            w = e.weight()
            if dist[e.from_ccy] + w < dist[e.to_ccy] - 1e-12:
                dist[e.to_ccy] = dist[e.from_ccy] + w
                pred[e.to_ccy] = e
                updated = True
        if not updated:
            break

    # One more pass: any further relaxation means the target is on a
    # negative cycle. Walk back |V| times to land on the cycle itself,
    # then walk the cycle once.
    cycles: list[Cycle] = []
    seen_keys: set[tuple[str, ...]] = set()

    for e in edges:
        w = e.weight()
        if dist[e.from_ccy] + w < dist[e.to_ccy] - 1e-12:
            cycle = _walk_cycle(pred, e.to_ccy, len(nodes))
            if cycle is None or len(cycle) != CYCLE_LENGTH:
                continue
            key = _canonical_key(cycle)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            cycles.append(_finalise(cycle))

    log.debug("brain.detect", n_edges=len(edges), n_cycles=len(cycles))
    return cycles


def _walk_cycle(
    pred: dict[str, Edge | None],
    start: str,
    n_nodes: int,
) -> list[Edge] | None:
    """Trace back through `pred` to find the cycle containing `start`."""
    node = start
    for _ in range(n_nodes):
        e = pred[node]
        if e is None:
            return None
        node = e.from_ccy

    # Now `node` is guaranteed to be on the cycle. Walk one full lap.
    legs: list[Edge] = []
    visited: dict[str, int] = {}
    cur = node
    while cur not in visited:
        visited[cur] = len(legs)
        e = pred[cur]
        if e is None:
            return None
        legs.append(e)
        cur = e.from_ccy
    # Trim any pre-cycle tail.
    start_idx = visited[cur]
    return list(reversed(legs[start_idx:]))


def _canonical_key(legs: list[Edge]) -> tuple[str, ...]:
    """Rotation-invariant key so we don't emit the same cycle twice."""
    pairs = [f"{e.from_ccy}->{e.to_ccy}" for e in legs]
    # Rotate so the lexicographically smallest pair comes first.
    pivot = min(range(len(pairs)), key=lambda i: pairs[i])
    return tuple(pairs[pivot:] + pairs[:pivot])


def _finalise(legs: list[Edge]) -> Cycle:
    """Sum the post-fee log returns of the legs."""
    total = sum(math.log(e.rate * (1.0 - e.fee)) for e in legs)
    return Cycle(legs=(legs[0], legs[1], legs[2]), log_return=total)
