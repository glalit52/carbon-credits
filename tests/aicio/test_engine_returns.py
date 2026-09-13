"""Return calculations, against closed-form answers."""

from __future__ import annotations

from datetime import date

import pytest

from aicio.engine.returns import (
    CashFlow, ReturnError, absolute_return, annualise, cagr, periodic_returns,
    rolling_returns, twrr, xirr,
)


def test_xirr_matches_the_closed_form():
    """₹50k two years ago and ₹50k one year ago, now ₹150k.

    Solving 50x² + 50x = 150 for x = 1 + r gives x = (√13 − 1)/2, so r is
    30.2776% a year in exact years. The engine uses an actual/365.25 day
    count, so 730 and 365 days are 1.9986 and 0.9993 years and the answer
    lands a shade above -- 30.30%. The tolerance spans that convention and
    nothing wider; a real regression moves this by whole percentage points.
    """
    flows = [
        CashFlow(date(2024, 9, 12), -50_000),
        CashFlow(date(2025, 9, 12), -50_000),
        CashFlow(date(2026, 9, 12), 150_000),
    ]
    assert xirr(flows) == pytest.approx(0.302776, abs=5e-4)


def test_xirr_on_a_single_period_is_the_simple_return():
    flows = [CashFlow(date(2025, 1, 1), -100), CashFlow(date(2026, 1, 1), 110)]
    assert xirr(flows) == pytest.approx(0.0999, abs=2e-3)


def test_xirr_handles_a_loss():
    flows = [CashFlow(date(2024, 1, 1), -100_000), CashFlow(date(2026, 1, 1), 80_000)]
    assert xirr(flows) < 0


def test_xirr_converges_from_a_bad_guess():
    """Newton's method wanders on lopsided flows; bisection has to catch it."""
    flows = [
        CashFlow(date(2020, 1, 1), -1_000),
        CashFlow(date(2020, 2, 1), -50_000),
        CashFlow(date(2026, 1, 1), 95_000),
    ]
    assert xirr(flows, guess=8.0) == pytest.approx(xirr(flows, guess=0.01), abs=1e-4)


@pytest.mark.parametrize("flows", [
    [CashFlow(date(2025, 1, 1), -100)],                                  # one flow
    [CashFlow(date(2025, 1, 1), -100), CashFlow(date(2026, 1, 1), -50)],  # all negative
])
def test_xirr_refuses_undefined_inputs(flows):
    with pytest.raises(ReturnError):
        xirr(flows)


def test_cagr():
    assert cagr(100, 200, 5) == pytest.approx(0.148698, abs=1e-6)


def test_cagr_refuses_to_annualise_a_short_period():
    """"380% annualised" off six weeks is the most misleading number in retail
    finance, so the engine will not produce it."""
    with pytest.raises(ReturnError):
        cagr(100, 130, 0.1)
    with pytest.raises(ReturnError):
        annualise(0.3, 0.1)


def test_cagr_needs_a_positive_base():
    with pytest.raises(ReturnError):
        cagr(0, 200, 5)


def test_twrr_strips_out_contribution_timing():
    """A fund that returns 10% twice is a 21% fund regardless of when money
    arrived; XIRR would say something different and both would be right."""
    assert twrr([(100, 120, 10), (120, 132, 0)]) == pytest.approx(0.21, abs=1e-9)


def test_twrr_needs_a_positive_start():
    with pytest.raises(ReturnError):
        twrr([(0, 100, 0)])


def test_absolute_return_is_safe_on_zero():
    assert absolute_return(0, 100) == 0.0
    assert absolute_return(100, 150) == pytest.approx(0.5)


def test_rolling_returns_finds_every_window():
    navs = [(date(2020 + y, 1, 1), 100 * 1.1 ** y) for y in range(6)]
    windows = rolling_returns(navs, 3)
    assert len(windows) == 3
    assert all(r == pytest.approx(0.1, abs=1e-3) for r in windows)


def test_periodic_returns_skips_non_positive_bases():
    assert periodic_returns([100, 110, 0, 50]) == pytest.approx([0.1, -1.0])
