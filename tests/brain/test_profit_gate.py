"""Tests for src/brain/profit_gate.py.

DESTINATION: tests/brain/test_profit_gate.py
"""

from __future__ import annotations

import pytest

from src.brain.cycles import Cycle, Edge
from src.brain.profit_gate import (
    BPS_TO_LOG,
    DEFAULT_BUFFER_BPS,
    passes,
)


def _cycle_with_log_return(lr: float) -> Cycle:
    """Tiny helper: build a Cycle with a synthetic log-return for testing
    the gate in isolation."""
    dummy = Edge("A", "B", rate=1.0, fee=0.0)
    return Cycle(legs=(dummy, dummy, dummy), log_return=lr)


# ---------------------------------------------------------------
# Basic decision behaviour
# ---------------------------------------------------------------


def test_passes_when_well_above_buffer() -> None:
    # 50 bps log-return easily clears a 5 bps buffer
    result = passes(_cycle_with_log_return(50.0 * BPS_TO_LOG))
    assert result.passed is True
    assert result.rejection_reason is None


def test_rejects_when_exactly_at_buffer() -> None:
    """Strict inequality: at threshold, we reject."""
    result = passes(
        _cycle_with_log_return(DEFAULT_BUFFER_BPS * BPS_TO_LOG)
    )
    assert result.passed is False
    assert result.rejection_reason == "post_fee_below_buffer"


def test_rejects_negative_return() -> None:
    result = passes(_cycle_with_log_return(-10.0 * BPS_TO_LOG))
    assert result.passed is False
    assert result.expected_return_bps == pytest.approx(-10.0)


# ---------------------------------------------------------------
# Buffer monotonicity property
# ---------------------------------------------------------------


@pytest.mark.parametrize("lr_bps", [3.0, 5.0, 10.0, 20.0, 50.0])
def test_higher_buffer_never_makes_more_cycles_pass(lr_bps: float) -> None:
    """If a cycle passes buffer B, it must also pass any lower buffer."""
    cycle = _cycle_with_log_return(lr_bps * BPS_TO_LOG)
    result_low = passes(cycle, buffer_bps=2.0)
    result_high = passes(cycle, buffer_bps=20.0)
    assert not (result_high.passed and not result_low.passed)


# ---------------------------------------------------------------
# Result content
# ---------------------------------------------------------------


def test_reports_expected_return_in_bps() -> None:
    result = passes(_cycle_with_log_return(13.0 * BPS_TO_LOG))
    assert result.expected_return_bps == pytest.approx(13.0)


def test_reports_applied_buffer() -> None:
    result = passes(_cycle_with_log_return(0.0), buffer_bps=7.5)
    assert result.buffer_bps == pytest.approx(7.5)
