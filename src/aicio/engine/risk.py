"""Risk: how far this can fall, and whether the owner survives it.

Volatility is the number the industry quotes and the number clients care least
about. What ends a financial plan is a drawdown arriving at the moment money is
needed, so this module treats drawdown, downside deviation and explicit
scenarios as first-class, and keeps standard deviation as one input among
several rather than as "the risk number".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

#: Trading days in a year. Used to annualise a daily series; a monthly series
#: passes ``periods_per_year=12`` instead.
TRADING_DAYS = 252

#: India's 10-year government bond has sat in this region for years. It is the
#: risk-free rate for a rupee investor, and it is a parameter rather than a
#: constant because a US user needs a different one.
DEFAULT_RISK_FREE = 0.068

#: Below this, a series is flat. A constant series does not produce a variance
#: of exactly zero in floating point -- it produces about 1e-17 -- and dividing
#: an excess return by that yields a Sharpe ratio in the quadrillions, which is
#: a number a user would see and a system would happily print.
_FLAT = 1e-12


class RiskError(ValueError):
    pass


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def volatility(returns: Sequence[float], *, periods_per_year: int = TRADING_DAYS) -> float:
    """Annualised standard deviation of returns.

    Sample standard deviation (n-1): these are observations drawn from an
    unknown distribution, not the population itself, and with the short series
    a retail portfolio actually has, the difference is not academic.
    """
    if len(returns) < 2:
        raise RiskError("volatility needs at least two observations")
    avg = _mean(returns)
    variance = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(periods_per_year)


def downside_deviation(
    returns: Sequence[float], *, target: float = 0.0, periods_per_year: int = TRADING_DAYS
) -> float:
    """Volatility of the downside only. Upside surprise is not risk."""
    if len(returns) < 2:
        raise RiskError("downside deviation needs at least two observations")
    shortfalls = [min(0.0, r - target) ** 2 for r in returns]
    return math.sqrt(sum(shortfalls) / (len(returns) - 1)) * math.sqrt(periods_per_year)


def drawdown_series(values: Sequence[float]) -> list[float]:
    """Fraction below the running peak at each point."""
    out: list[float] = []
    peak = float("-inf")
    for value in values:
        peak = max(peak, value)
        out.append(0.0 if peak <= 0 else value / peak - 1.0)
    return out


@dataclass(frozen=True)
class Drawdown:
    depth: float                # negative fraction
    peak_index: int
    trough_index: int
    recovery_index: int | None  # None while still under water

    @property
    def recovered(self) -> bool:
        return self.recovery_index is not None


def max_drawdown(values: Sequence[float]) -> Drawdown:
    """Worst peak-to-trough fall, with the recovery point if it came.

    Time under water is reported alongside depth because a 30% fall that
    recovers in four months and a 30% fall still unrecovered after three years
    are different experiences, and only one of them breaks a goal.
    """
    if len(values) < 2:
        raise RiskError("drawdown needs at least two observations")
    peak = values[0]
    peak_index = 0
    worst = Drawdown(0.0, 0, 0, 0)
    for index, value in enumerate(values):
        if value > peak:
            peak, peak_index = value, index
        depth = 0.0 if peak <= 0 else value / peak - 1.0
        if depth < worst.depth:
            worst = Drawdown(depth, peak_index, index, None)
    if worst.depth < 0:
        peak_value = values[worst.peak_index]
        for index in range(worst.trough_index + 1, len(values)):
            if values[index] >= peak_value:
                return Drawdown(worst.depth, worst.peak_index, worst.trough_index, index)
    return worst


def sharpe(
    returns: Sequence[float],
    *,
    risk_free: float = DEFAULT_RISK_FREE,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    vol = volatility(returns, periods_per_year=periods_per_year)
    if vol < _FLAT:
        raise RiskError("Sharpe is undefined for a zero-volatility series")
    excess = _mean(returns) * periods_per_year - risk_free
    return excess / vol


def sortino(
    returns: Sequence[float],
    *,
    risk_free: float = DEFAULT_RISK_FREE,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    target = risk_free / periods_per_year
    deviation = downside_deviation(returns, target=target, periods_per_year=periods_per_year)
    if deviation < _FLAT:
        raise RiskError("Sortino is undefined when nothing fell below target")
    excess = _mean(returns) * periods_per_year - risk_free
    return excess / deviation


def beta(asset_returns: Sequence[float], market_returns: Sequence[float]) -> float:
    if len(asset_returns) != len(market_returns) or len(asset_returns) < 2:
        raise RiskError("beta needs two aligned series of at least two points")
    asset_avg, market_avg = _mean(asset_returns), _mean(market_returns)
    covariance = sum(
        (a - asset_avg) * (m - market_avg) for a, m in zip(asset_returns, market_returns)
    )
    variance = sum((m - market_avg) ** 2 for m in market_returns)
    if variance < _FLAT:
        raise RiskError("beta is undefined against a flat market")
    return covariance / variance


def historical_var(returns: Sequence[float], *, confidence: float = 0.95) -> float:
    """Loss not exceeded with ``confidence`` probability, from the empirical
    distribution rather than a normal assumption -- returns are not normal and
    the tail is exactly the part being measured."""
    if not 0.5 < confidence < 1.0:
        raise RiskError("confidence must be between 0.5 and 1")
    if len(returns) < 20:
        raise RiskError("historical VaR needs at least 20 observations to mean anything")
    ordered = sorted(returns)
    index = int((1 - confidence) * len(ordered))
    return ordered[min(index, len(ordered) - 1)]


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Shock:
    """A named stress, expressed per asset class."""

    name: str
    moves: dict[str, float]              # asset class value -> fractional move
    description: str = ""


#: The standard battery. Equity shocks are the PRD's -20/-30/-50; the others
#: exist because the questions clients actually ask are "what if I lose my job"
#: and "what if rates move", not "what is my 95% VaR".
STANDARD_SHOCKS: tuple[Shock, ...] = (
    Shock("equity_-20", {"equity": -0.20, "crypto": -0.35, "real_estate": -0.08},
          "A routine correction; one happens roughly every other year."),
    Shock("equity_-30", {"equity": -0.30, "crypto": -0.50, "real_estate": -0.12, "gold": 0.05},
          "A bear market on the scale of 2008's first leg or March 2020."),
    Shock("equity_-50", {"equity": -0.50, "crypto": -0.70, "real_estate": -0.25, "gold": 0.12,
                         "debt": -0.02},
          "A generational crash. Rare, and the one that ends plans."),
    Shock("rates_+200bp", {"debt": -0.08, "equity": -0.07, "real_estate": -0.10},
          "A sharp rise in rates: long-duration debt falls with equity."),
    Shock("inflation_shock", {"debt": -0.05, "equity": -0.10, "gold": 0.15},
          "Inflation surprises upward; real assets hold, nominal ones do not."),
)


@dataclass
class ScenarioResult:
    name: str
    description: str
    value_before: float
    value_after: float
    #: The shock that was applied, per asset class. Carried on the result so a
    #: reader -- or the grounding check -- can see that "a 50% equity fall"
    #: came from the scenario definition rather than from nowhere.
    moves: dict[str, float] = field(default_factory=dict)
    #: Months of expenses the liquid part of the portfolio still covers after
    #: the shock. The number that decides whether a fall is survivable.
    liquidity_months_after: float | None = None
    goal_impact: dict[str, float] = field(default_factory=dict)

    @property
    def loss(self) -> float:
        return self.value_after - self.value_before

    @property
    def loss_pct(self) -> float:
        return 0.0 if self.value_before == 0 else self.loss / self.value_before

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "value_before": round(self.value_before, 2),
            "value_after": round(self.value_after, 2),
            "loss": round(self.loss, 2),
            "loss_pct": round(self.loss_pct, 6),
            "moves": {k: round(v, 4) for k, v in self.moves.items()},
            "liquidity_months_after": (
                None if self.liquidity_months_after is None
                else round(self.liquidity_months_after, 2)
            ),
            "goal_impact": {k: round(v, 6) for k, v in self.goal_impact.items()},
        }


def scenario_test(
    exposure: dict[str, float],
    shock: Shock,
    *,
    monthly_expenses: float = 0.0,
    liquid_classes: Iterable[str] = ("cash", "debt"),
) -> ScenarioResult:
    """Apply one shock to an exposure map of asset class -> value."""
    before = sum(exposure.values())
    after_by_class = {
        name: value * (1 + shock.moves.get(name, 0.0)) for name, value in exposure.items()
    }
    after = sum(after_by_class.values())
    liquidity = None
    if monthly_expenses > 0:
        liquid = sum(after_by_class.get(name, 0.0) for name in liquid_classes)
        liquidity = liquid / monthly_expenses
    return ScenarioResult(
        shock.name, shock.description, before, after,
        moves=dict(shock.moves), liquidity_months_after=liquidity,
    )


def run_scenarios(
    exposure: dict[str, float],
    *,
    monthly_expenses: float = 0.0,
    shocks: Iterable[Shock] = STANDARD_SHOCKS,
) -> list[ScenarioResult]:
    return [scenario_test(exposure, s, monthly_expenses=monthly_expenses) for s in shocks]


def risk_capacity_score(
    *,
    horizon_years: float,
    income_stability: str,
    dependents: int,
    emergency_months: float,
    debt_to_income: float,
) -> int:
    """Measured capacity to absorb loss, on the same 1-10 scale as tolerance.

    Kept deterministic and explainable on purpose: a user who disagrees with
    their capacity score can be shown exactly which input produced it, which
    is not possible with a fitted model and matters more than the extra
    accuracy a fitted model might buy.
    """
    score = 5.0
    score += min(3.0, horizon_years / 7.0)
    score += {"stable": 1.0, "variable": -0.5, "concentrated": -1.5}.get(income_stability, 0.0)
    score -= min(1.5, dependents * 0.5)
    score += 1.0 if emergency_months >= 6 else (-1.5 if emergency_months < 3 else 0.0)
    score -= min(2.0, max(0.0, debt_to_income - 0.3) * 4)
    return int(max(1, min(10, round(score))))
