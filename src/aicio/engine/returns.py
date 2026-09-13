"""Return calculations.

The distinction that matters to a user, and that most apps get wrong:

*   **XIRR** answers "what did *my* money earn", because it weights every
    rupee by how long it was actually invested. It is the right number for a
    portfolio built by SIPs.
*   **TWRR** answers "how good was the *fund*", because it strips out the
    timing of contributions the manager did not control. It is the right
    number for comparing a fund to its benchmark.

Reporting one where the other belongs makes a good fund look bad in a rising
market, or flatters a bad one, so both are implemented and each is labelled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Sequence

from ..money import as_float

DAYS_PER_YEAR = 365.25

#: XIRR is a root-find on a polynomial that can be badly behaved for short,
#: lopsided cash-flow sets. These bounds bracket every plausible real answer
#: (-99.99% to +10,000% annualised) and let us fall back to bisection, which
#: cannot diverge, when Newton's method wanders.
_RATE_FLOOR = -0.9999
_RATE_CEILING = 100.0


class ReturnError(ValueError):
    """Raised when a return is not defined for the inputs given."""


@dataclass(frozen=True)
class CashFlow:
    on: date
    amount: float          # investor sign convention: outflow negative

    @classmethod
    def of(cls, on: date, amount: Decimal | float) -> "CashFlow":
        return cls(on, as_float(amount))


def _npv(rate: float, flows: Sequence[CashFlow], origin: date) -> float:
    total = 0.0
    for flow in flows:
        years = (flow.on - origin).days / DAYS_PER_YEAR
        total += flow.amount / (1.0 + rate) ** years
    return total


def xirr(flows: Iterable[CashFlow], *, guess: float = 0.12, tolerance: float = 1e-7) -> float:
    """Internal rate of return for irregularly timed cash flows.

    Newton's method first because it converges in a handful of iterations for
    ordinary portfolios; bisection afterwards because Newton's method is not
    guaranteed to converge at all and a wealth report cannot return "maybe".
    """
    flows = sorted(flows, key=lambda f: f.on)
    if len(flows) < 2:
        raise ReturnError("XIRR needs at least two cash flows")
    if not (any(f.amount > 0 for f in flows) and any(f.amount < 0 for f in flows)):
        raise ReturnError("XIRR needs both a positive and a negative cash flow")

    origin = flows[0].on
    rate = guess
    for _ in range(60):
        value = _npv(rate, flows, origin)
        if abs(value) < tolerance:
            return rate
        # Numerical derivative: the analytic one is no more accurate here and
        # is easy to get subtly wrong with fractional exponents.
        step = 1e-6
        slope = (_npv(rate + step, flows, origin) - value) / step
        if abs(slope) < 1e-12:
            break
        nxt = rate - value / slope
        if not (_RATE_FLOOR < nxt < _RATE_CEILING):
            break
        if abs(nxt - rate) < tolerance:
            return nxt
        rate = nxt

    low, high = _RATE_FLOOR + 1e-9, _RATE_CEILING
    f_low = _npv(low, flows, origin)
    f_high = _npv(high, flows, origin)
    if f_low * f_high > 0:
        raise ReturnError("XIRR did not bracket a root; cash flows may be degenerate")
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = _npv(mid, flows, origin)
        if abs(f_mid) < tolerance or (high - low) < tolerance:
            return mid
        if f_low * f_mid < 0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2


def cagr(begin_value: float, end_value: float, years: float) -> float:
    """Compound annual growth rate.

    Undefined for a non-positive start, and refuses to annualise sub-year
    periods: "this fund returned 380% annualised" off six weeks of data is the
    single most misleading number in retail finance.
    """
    if begin_value <= 0:
        raise ReturnError("CAGR needs a positive starting value")
    if years <= 0:
        raise ReturnError("CAGR needs a positive period")
    if years < 1.0:
        raise ReturnError("refusing to annualise a period shorter than one year")
    return (end_value / begin_value) ** (1.0 / years) - 1.0


def absolute_return(invested: Decimal | float, current: Decimal | float) -> float:
    invested_f = as_float(invested)
    if invested_f == 0:
        return 0.0
    return (as_float(current) - invested_f) / invested_f


def twrr(periods: Sequence[tuple[float, float, float]]) -> float:
    """Time-weighted return from (start_value, end_value, net_flow) periods.

    ``net_flow`` is money added during the period, and is removed from the end
    value before measuring growth, so contributions neither help nor hurt the
    measured performance.
    """
    if not periods:
        raise ReturnError("TWRR needs at least one period")
    compounded = 1.0
    for start, end, flow in periods:
        if start <= 0:
            raise ReturnError("TWRR period needs a positive starting value")
        compounded *= (end - flow) / start
    return compounded - 1.0


def annualise(total_return: float, years: float) -> float:
    if years <= 0:
        raise ReturnError("cannot annualise over a non-positive period")
    if years < 1.0:
        raise ReturnError("refusing to annualise a period shorter than one year")
    return (1.0 + total_return) ** (1.0 / years) - 1.0


def rolling_returns(navs: Sequence[tuple[date, float]], window_years: float) -> list[float]:
    """Every overlapping ``window_years`` return in a NAV series.

    Point-to-point returns depend entirely on the endpoints chosen; rolling
    returns are how you tell a consistent fund from a lucky one, which is the
    difference the PRD's fund intelligence section is asking for.
    """
    if window_years <= 0:
        raise ReturnError("window must be positive")
    series = sorted(navs, key=lambda item: item[0])
    window_days = window_years * DAYS_PER_YEAR
    out: list[float] = []
    right = 0
    for left, (start_date, start_nav) in enumerate(series):
        if start_nav <= 0:
            continue
        right = max(right, left)
        while right < len(series) and (series[right][0] - start_date).days < window_days:
            right += 1
        if right >= len(series):
            break
        end_nav = series[right][1]
        years = (series[right][0] - start_date).days / DAYS_PER_YEAR
        if years <= 0:
            continue
        out.append((end_nav / start_nav) ** (1 / years) - 1 if years >= 1 else end_nav / start_nav - 1)
    return out


def periodic_returns(values: Sequence[float]) -> list[float]:
    """Simple period-over-period returns, skipping non-positive bases."""
    out: list[float] = []
    for previous, current in zip(values, values[1:]):
        if previous <= 0:
            continue
        out.append(current / previous - 1.0)
    return out
