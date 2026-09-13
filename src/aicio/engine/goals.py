"""Goal projection.

Two things this module refuses to do, both of them things most goal calculators
do happily:

*   **Report a single number.** "You will have ₹4.2 crore" is false precision
    over a twenty-year horizon. Output is a distribution, and the headline is a
    probability of reaching the goal.
*   **Hide its assumptions.** Every return and volatility figure used is an
    explicit :class:`CapitalMarketAssumptions` field, returned with the result
    so the user can disagree with it. A projection whose inputs are invisible
    cannot be argued with, and one that cannot be argued with should not be
    trusted.

The simulation is seeded. Same inputs, same answer -- required by the PRD's
consistency eval and by the rule that a stored recommendation must be
reproducible.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Sequence

from ..domain import AssetClass, Goal
from ..money import as_float


@dataclass(frozen=True)
class CapitalMarketAssumptions:
    """Long-run nominal expectations for an Indian rupee investor.

    Deliberately unexciting. These are planning assumptions, not forecasts, and
    they are set below recent trailing returns on purpose: a plan that only
    works if the next decade matches the last one is not a plan.
    """

    expected: dict[AssetClass, float] = field(default_factory=lambda: {
        AssetClass.EQUITY: 0.11,
        AssetClass.DEBT: 0.065,
        AssetClass.GOLD: 0.07,
        AssetClass.CASH: 0.04,
        AssetClass.REAL_ESTATE: 0.07,
        AssetClass.ALTERNATIVE: 0.08,
        AssetClass.CRYPTO: 0.10,
        AssetClass.OTHER: 0.05,
    })
    volatility: dict[AssetClass, float] = field(default_factory=lambda: {
        AssetClass.EQUITY: 0.16,
        AssetClass.DEBT: 0.04,
        AssetClass.GOLD: 0.14,
        AssetClass.CASH: 0.005,
        AssetClass.REAL_ESTATE: 0.12,
        AssetClass.ALTERNATIVE: 0.15,
        AssetClass.CRYPTO: 0.60,
        AssetClass.OTHER: 0.10,
    })
    inflation: float = 0.06
    #: Correlation between the risky classes. One number rather than a matrix:
    #: with four classes and twenty-year horizons, the extra precision of a
    #: full matrix is swamped by the uncertainty in the means.
    cross_correlation: float = 0.35
    source: str = "aicio planning assumptions v1"

    def portfolio_return(self, weights: dict[AssetClass, float]) -> float:
        return sum(self.expected.get(k, 0.05) * w for k, w in weights.items())

    def portfolio_volatility(self, weights: dict[AssetClass, float]) -> float:
        """Correlated volatility.

        The naive version -- weighting standard deviations -- overstates risk
        badly for a diversified portfolio, and the fully independent version
        understates it just as badly in exactly the crash where it matters.
        A single positive cross-correlation lands between the two.
        """
        variance = 0.0
        items = list(weights.items())
        for i, (class_i, weight_i) in enumerate(items):
            vol_i = self.volatility.get(class_i, 0.10)
            for j, (class_j, weight_j) in enumerate(items):
                vol_j = self.volatility.get(class_j, 0.10)
                rho = 1.0 if i == j else self.cross_correlation
                variance += weight_i * weight_j * vol_i * vol_j * rho
        return math.sqrt(max(0.0, variance))

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected": {k.value: v for k, v in self.expected.items()},
            "volatility": {k.value: v for k, v in self.volatility.items()},
            "inflation": self.inflation,
            "cross_correlation": self.cross_correlation,
            "source": self.source,
        }


DEFAULT_CMA = CapitalMarketAssumptions()


@dataclass
class GoalProjection:
    goal_id: str
    goal_name: str
    years: float
    target_nominal: float
    current_value: float
    monthly_contribution: float
    expected_return: float
    expected_volatility: float
    #: Deterministic path, for the "if everything goes to plan" line.
    expected_value: float = 0.0
    percentiles: dict[str, float] = field(default_factory=dict)
    probability: float = 0.0
    shortfall: float = 0.0
    required_monthly: float = 0.0
    assumptions: dict[str, Any] = field(default_factory=dict)
    trials: int = 0

    @property
    def on_track(self) -> bool:
        """Above 70% is the product's definition of on track.

        Not 50% -- a coin flip on a child's education is not "on track" -- and
        not 95%, which would push every user into over-saving for goals that
        have twenty years to self-correct.
        """
        return self.probability >= 0.70

    @property
    def status(self) -> str:
        if self.probability >= 0.85:
            return "comfortable"
        if self.probability >= 0.70:
            return "on_track"
        if self.probability >= 0.45:
            return "at_risk"
        return "off_track"

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "goal_name": self.goal_name,
            "years": round(self.years, 2),
            "target_nominal": round(self.target_nominal, 2),
            "current_value": round(self.current_value, 2),
            "monthly_contribution": round(self.monthly_contribution, 2),
            "expected_return": round(self.expected_return, 6),
            "expected_volatility": round(self.expected_volatility, 6),
            "expected_value": round(self.expected_value, 2),
            "percentiles": {k: round(v, 2) for k, v in self.percentiles.items()},
            "probability": round(self.probability, 4),
            "status": self.status,
            "on_track": self.on_track,
            "shortfall": round(self.shortfall, 2),
            "required_monthly": round(self.required_monthly, 2),
            "trials": self.trials,
            "assumptions": self.assumptions,
        }


def future_value(
    present: float, monthly: float, annual_return: float, years: float
) -> float:
    """Deterministic growth of a lump sum plus a monthly contribution."""
    months = int(round(years * 12))
    if months <= 0:
        return present
    rate = (1 + annual_return) ** (1 / 12) - 1
    value = present * (1 + rate) ** months
    if rate == 0:
        return value + monthly * months
    # Contributions are made at the start of each month, which is what a SIP
    # mandate actually does; the (1 + rate) factor is that extra month of growth.
    return value + monthly * (((1 + rate) ** months - 1) / rate) * (1 + rate)


def required_contribution(
    target: float, present: float, annual_return: float, years: float
) -> float:
    """Monthly amount needed to close the gap. Zero if already there."""
    months = int(round(years * 12))
    if months <= 0:
        return max(0.0, target - present)
    rate = (1 + annual_return) ** (1 / 12) - 1
    grown = present * (1 + rate) ** months
    gap = target - grown
    if gap <= 0:
        return 0.0
    if rate == 0:
        return gap / months
    return gap / ((((1 + rate) ** months - 1) / rate) * (1 + rate))


def simulate_goal(
    *,
    present: float,
    monthly: float,
    annual_return: float,
    annual_volatility: float,
    years: float,
    target: float,
    trials: int = 4000,
    seed: int = 20260912,
    contribution_growth: float = 0.0,
) -> tuple[dict[str, float], float]:
    """Monte Carlo over monthly log-normal returns.

    Log-normal rather than normal because a portfolio cannot fall more than
    100%, and a normal model quietly assigns probability to that impossibility
    -- which matters exactly in the left tail the user is asking about.

    Returns ``(percentiles, probability_of_reaching_target)``.
    """
    months = max(1, int(round(years * 12)))
    rng = random.Random(seed)

    # Convert the arithmetic annual figure to the log-space parameters of the
    # monthly step. Calibrated so the simulated *mean* compounds at the stated
    # rate, which is what an expected return means.
    #
    # The consequence is deliberate and worth stating: the median path lands
    # below the mean, by more the more volatile the portfolio is. That gap is
    # volatility drag, it is real, and it is precisely why this module reports
    # a distribution rather than the single number a deterministic projection
    # would give -- which is the mean, and which half of all outcomes miss.
    monthly_vol = annual_volatility / math.sqrt(12)
    monthly_mean = (1 + annual_return) ** (1 / 12) - 1
    mu = math.log(1 + monthly_mean) - 0.5 * monthly_vol ** 2

    outcomes: list[float] = []
    for _ in range(trials):
        value = present
        contribution = monthly
        for month in range(months):
            if month and month % 12 == 0 and contribution_growth:
                contribution *= 1 + contribution_growth
            value += contribution
            shock = rng.gauss(mu, monthly_vol) if monthly_vol > 0 else mu
            value *= math.exp(shock)
        outcomes.append(value)

    outcomes.sort()
    def at(p: float) -> float:
        index = min(len(outcomes) - 1, max(0, int(p * len(outcomes))))
        return outcomes[index]

    percentiles = {
        "p05": at(0.05), "p10": at(0.10), "p25": at(0.25), "p50": at(0.50),
        "p75": at(0.75), "p90": at(0.90), "p95": at(0.95),
    }
    success = sum(1 for value in outcomes if value >= target) / len(outcomes)
    return percentiles, success


def project_goal(
    goal: Goal,
    *,
    current_value: float,
    monthly_contribution: float,
    weights: dict[AssetClass, float],
    today: date,
    cma: CapitalMarketAssumptions = DEFAULT_CMA,
    trials: int = 4000,
    seed: int = 20260912,
) -> GoalProjection:
    """Full projection for one goal against the portfolio funding it.

    ``today`` is required rather than defaulted. A projection that reads the
    clock cannot be re-derived later, which breaks the one promise that makes
    a stored recommendation explainable: run the engine on exactly what it saw
    and get exactly what it said.
    """
    years = goal.years_remaining(today=today)
    target = as_float(goal.inflated_target(today=today))
    expected = cma.portfolio_return(weights) if weights else cma.expected[AssetClass.DEBT]
    vol = cma.portfolio_volatility(weights) if weights else 0.04

    # The deterministic line is the mean path. It sits above the median for any
    # volatile portfolio, so it is reported alongside the percentiles rather
    # than instead of them.
    deterministic = future_value(current_value, monthly_contribution, expected, years)
    percentiles, probability = simulate_goal(
        present=current_value,
        monthly=monthly_contribution,
        annual_return=expected,
        annual_volatility=vol,
        years=years,
        target=target,
        trials=trials,
        seed=seed,
    )
    needed = required_contribution(target, current_value, expected, years)
    return GoalProjection(
        goal_id=goal.id,
        goal_name=goal.name,
        years=years,
        target_nominal=target,
        current_value=current_value,
        monthly_contribution=monthly_contribution,
        expected_return=expected,
        expected_volatility=vol,
        expected_value=deterministic,
        percentiles=percentiles,
        probability=probability,
        shortfall=max(0.0, target - percentiles["p50"]),
        required_monthly=needed,
        trials=trials,
        assumptions={
            "inflation": goal.inflation_rate,
            "expected_return": round(expected, 4),
            "expected_volatility": round(vol, 4),
            "capital_market_assumptions": cma.source,
            "target_is_inflated": True,
        },
    )


def scenario_compare(
    goal: Goal,
    *,
    current_value: float,
    monthly_contribution: float,
    weights: dict[AssetClass, float],
    today: date,
    cma: CapitalMarketAssumptions = DEFAULT_CMA,
    contribution_deltas: Sequence[float] = (0.0, 5000.0, 10000.0),
    year_deltas: Sequence[int] = (0, 2, -2),
    trials: int = 1500,
) -> list[dict[str, Any]]:
    """What actually moves the needle: more money, or more time.

    Presented side by side because the honest answer is usually "delay by two
    years", and a product that only offers "invest more" is selling, not
    advising.
    """
    base_years = goal.years_remaining(today=today)
    expected = cma.portfolio_return(weights) if weights else 0.065
    vol = cma.portfolio_volatility(weights) if weights else 0.04
    out: list[dict[str, Any]] = []
    for extra in contribution_deltas:
        for year_delta in year_deltas:
            years = max(0.5, base_years + year_delta)
            target = as_float(goal.target_amount) * (1 + goal.inflation_rate) ** years
            _, probability = simulate_goal(
                present=current_value,
                monthly=monthly_contribution + extra,
                annual_return=expected,
                annual_volatility=vol,
                years=years,
                target=target,
                trials=trials,
            )
            out.append({
                "extra_monthly": extra,
                "year_delta": year_delta,
                "years": round(years, 2),
                "target_nominal": round(target, 2),
                "probability": round(probability, 4),
            })
    return sorted(out, key=lambda row: (-row["probability"], row["extra_monthly"]))
