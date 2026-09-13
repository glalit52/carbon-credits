"""Deterministic financial analytics.

The rule for this package, enforced by ``tests/aicio/test_evals_and_purity.py``:
no network, no LLM, no clock reads hidden inside a calculation. Everything is
a pure function of its arguments, so the same portfolio always produces the
same numbers and a three-month-old recommendation can be re-derived exactly.

That is not fastidiousness. A wealth product's single unrecoverable failure is
a wrong number presented confidently, and the only defence that scales is
keeping the arithmetic somewhere a language model cannot reach.
"""

from __future__ import annotations

from .allocation import allocation_breakdown, concentration, drift_report
from .goals import project_goal, simulate_goal
from .health import health_score
from .returns import absolute_return, cagr, twrr, xirr
from .risk import (
    drawdown_series, max_drawdown, scenario_test, sharpe, sortino, volatility,
)
from .sip import optimise_sips
from .taxlots import build_lots, realised_gains, tax_summary, unrealised_gains
from .xray import fund_overlap, look_through

__all__ = [
    "absolute_return", "cagr", "twrr", "xirr",
    "volatility", "max_drawdown", "drawdown_series", "sharpe", "sortino", "scenario_test",
    "allocation_breakdown", "drift_report", "concentration",
    "look_through", "fund_overlap",
    "build_lots", "realised_gains", "unrealised_gains", "tax_summary",
    "project_goal", "simulate_goal",
    "health_score",
    "optimise_sips",
]
