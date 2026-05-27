"""Gate 1 of the Triple-Gate pipeline: post-fee profitability filter.

Rejects cycles whose expected log-return doesn't exceed the slippage
buffer. The fee economics are already embedded in the cycle's
log_return (computed by src/brain/cycles.py), so this gate is a
pure threshold check.

DESTINATION: src/brain/profit_gate.py

References:
    - TECHNICAL_PLAN.md §3 (Profit Gate)
    - Default buffer: 5 bps (tunable per pair via env)
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.brain.cycles import Cycle

log = structlog.get_logger(__name__)

# 1 basis point = 1e-4 in absolute terms; we convert to log-space.
BPS_TO_LOG: float = 1.0e-4

DEFAULT_BUFFER_BPS: float = 5.0


@dataclass(frozen=True)
class ProfitGateResult:
    passed: bool
    expected_return_bps: float       # cycle's log-return converted to bps
    buffer_bps: float                # threshold applied
    rejection_reason: str | None     # None iff passed


def passes(
    cycle: Cycle,
    buffer_bps: float = DEFAULT_BUFFER_BPS,
) -> ProfitGateResult:
    """Decide whether `cycle` clears the post-fee profitability bar.

    The cycle's `log_return` is already net of taker fees. The buffer
    is an additional margin that absorbs queue-position uncertainty
    and any per-leg slippage we couldn't predict.

    Args:
        cycle: a Cycle produced by `src.brain.cycles.detect_negative_cycles`.
        buffer_bps: required edge above 0, in basis points.

    Returns:
        ProfitGateResult — boolean decision plus audit-trail fields.
    """
    threshold_log = buffer_bps * BPS_TO_LOG
    return_bps = cycle.log_return / BPS_TO_LOG

    if cycle.log_return > threshold_log:
        return ProfitGateResult(
            passed=True,
            expected_return_bps=return_bps,
            buffer_bps=buffer_bps,
            rejection_reason=None,
        )

    return ProfitGateResult(
        passed=False,
        expected_return_bps=return_bps,
        buffer_bps=buffer_bps,
        rejection_reason="post_fee_below_buffer",
    )
