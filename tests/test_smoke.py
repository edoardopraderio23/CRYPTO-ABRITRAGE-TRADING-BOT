"""Smoke tests: verify the package imports and CI is wired up.

These tests intentionally do nothing useful. They exist so that the
test infrastructure (pytest + coverage + CI) has a known-passing
baseline. Real unit tests for the Brain, Guardian, and Sentinel
will be added on the May 7 / 14 milestones.
"""


def test_pytest_is_wired_up() -> None:
    """Confirms pytest discovers and runs tests."""
    assert 1 + 1 == 2


def test_arithmetic_invariants() -> None:
    """A second trivial test, so coverage reporting has multiple data points."""
    assert 2 * 3 == 6
    assert 10 % 3 == 1


def test_log_price_property() -> None:
    """A property that the Brain's edge-weight formula relies on:
    ln(a * b) == ln(a) + ln(b). If this ever fails, math is broken.
    """
    import math
    a, b = 1.5, 2.7
    assert math.isclose(math.log(a * b), math.log(a) + math.log(b))
