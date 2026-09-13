"""Allocation, drift and concentration.

Allocation is computed on *market value*, split by the true class of each
instrument rather than by its label. A balanced fund holding 65% equity counts
as 65% equity here, because the alternative -- counting it wherever the fund
house filed it -- is how a portfolio ends up 20 points more aggressive than its
owner believes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain import AssetClass, Portfolio
from ..ips import InvestmentPolicy
from ..money import as_float


@dataclass
class AllocationBreakdown:
    by_class: dict[AssetClass, float]        # absolute value
    weights: dict[AssetClass, float]         # fraction of total
    total: float

    def weight(self, asset_class: AssetClass) -> float:
        return self.weights.get(asset_class, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 2),
            "by_class": {k.value: round(v, 2) for k, v in self.by_class.items()},
            "weights": {k.value: round(v, 6) for k, v in self.weights.items()},
        }


def allocation_breakdown(portfolio: Portfolio, *, include_cash: bool = True) -> AllocationBreakdown:
    by_class: dict[AssetClass, float] = {}
    for holding in portfolio.holdings:
        asset = portfolio.asset(holding.asset_id)
        value = as_float(holding.market_value)
        for asset_class, share in asset.class_split().items():
            by_class[asset_class] = by_class.get(asset_class, 0.0) + value * share
    if include_cash and portfolio.cash:
        cash = as_float(portfolio.cash)
        by_class[AssetClass.CASH] = by_class.get(AssetClass.CASH, 0.0) + cash

    total = sum(by_class.values())
    weights = {k: (v / total if total else 0.0) for k, v in by_class.items()}
    return AllocationBreakdown(by_class, weights, total)


@dataclass
class Drift:
    asset_class: AssetClass
    actual: float
    target: float
    lower: float
    upper: float
    value: float

    @property
    def gap(self) -> float:
        return self.actual - self.target

    @property
    def breach(self) -> float:
        """0 inside the band; signed distance outside it."""
        if self.actual < self.lower:
            return self.actual - self.lower
        if self.actual > self.upper:
            return self.actual - self.upper
        return 0.0

    @property
    def in_band(self) -> bool:
        return self.breach == 0.0

    def rupees_to_target(self, portfolio_total: float) -> float:
        """Money that would have to move to land on target. Negative means
        sell. This is the number a user can act on; a percentage is not."""
        return (self.target - self.actual) * portfolio_total

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_class": self.asset_class.value,
            "actual": round(self.actual, 6),
            "target": round(self.target, 6),
            "lower": round(self.lower, 6),
            "upper": round(self.upper, 6),
            "gap": round(self.gap, 6),
            "breach": round(self.breach, 6),
            "in_band": self.in_band,
            "value": round(self.value, 2),
        }


@dataclass
class DriftReport:
    drifts: list[Drift]
    total: float

    @property
    def breaches(self) -> list[Drift]:
        return [d for d in self.drifts if not d.in_band]

    @property
    def worst(self) -> Drift | None:
        if not self.drifts:
            return None
        return max(self.drifts, key=lambda d: abs(d.breach))

    @property
    def total_absolute_drift(self) -> float:
        """Sum of absolute gaps, halved.

        Halved because every rupee overweight in one class is the same rupee
        underweight in another; not halving double-counts the same drift and
        makes a mildly tilted portfolio look twice as far off as it is.
        """
        return sum(abs(d.gap) for d in self.drifts) / 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 2),
            "total_absolute_drift": round(self.total_absolute_drift, 6),
            "drifts": [d.to_dict() for d in self.drifts],
        }


def drift_report(breakdown: AllocationBreakdown, policy: InvestmentPolicy) -> DriftReport:
    drifts: list[Drift] = []
    seen: set[AssetClass] = set()
    for band in policy.bands:
        actual = breakdown.weight(band.asset_class)
        drifts.append(Drift(
            asset_class=band.asset_class,
            actual=actual,
            target=band.target,
            lower=band.lower,
            upper=band.upper,
            value=breakdown.by_class.get(band.asset_class, 0.0),
        ))
        seen.add(band.asset_class)
    # Classes the policy says nothing about still count: an unplanned 12% in
    # crypto is drift even though no band mentions it.
    for asset_class, weight in breakdown.weights.items():
        if asset_class not in seen and weight > 0:
            drifts.append(Drift(
                asset_class=asset_class, actual=weight, target=0.0, lower=0.0, upper=0.02,
                value=breakdown.by_class[asset_class],
            ))
    return DriftReport(drifts, breakdown.total)


@dataclass
class Concentration:
    """Herfindahl-Hirschman concentration plus the positions that cause it."""

    hhi: float
    effective_positions: float
    top: list[tuple[str, str, float]]        # (asset id, label, weight)
    breaches: list[tuple[str, str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hhi": round(self.hhi, 6),
            "effective_positions": round(self.effective_positions, 2),
            "top": [{"asset_id": a, "label": l, "weight": round(w, 6)} for a, l, w in self.top],
            "breaches": [
                {"asset_id": a, "label": l, "weight": round(w, 6)} for a, l, w in self.breaches
            ],
        }


#: A single *fund* position above this share is worth raising -- not as
#: single-name risk, which look-through measures, but as manager and process
#: risk. Set well above the single-name limit on purpose: three funds is a
#: perfectly sensible portfolio, and a 10% limit here would say otherwise.
POSITION_LIMIT = 0.35


def concentration(
    portfolio: Portfolio, *, limit: float = POSITION_LIMIT, top_n: int = 10
) -> Concentration:
    """Position-level concentration.

    ``effective_positions`` is 1/HHI: the number of equally sized holdings that
    would give the same concentration. Telling a user they hold "42 funds but
    are effectively holding 6 positions" lands in a way that an HHI of 0.16
    never does.

    Cash is in the denominator but is not ranked as a position. Leaving it out
    would make every weight here disagree with the same weight on the
    dashboard, and a product whose two screens quote different percentages for
    the same holding has already lost the argument about whether to trust it.
    """
    totals: dict[str, float] = {}
    for holding in portfolio.holdings:
        totals[holding.asset_id] = totals.get(holding.asset_id, 0.0) + as_float(holding.market_value)
    total = sum(totals.values()) + as_float(portfolio.cash)
    if total <= 0:
        return Concentration(0.0, 0.0, [], [])

    weights = {asset_id: value / total for asset_id, value in totals.items()}
    # HHI is measured over the invested positions only: cash is not a bet, and
    # counting it would make a cash-heavy portfolio look diversified.
    invested_total = sum(totals.values())
    hhi = sum((value / invested_total) ** 2 for value in totals.values()) if invested_total else 0.0
    ranked = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)

    def label(asset_id: str) -> str:
        asset = portfolio.assets.get(asset_id)
        return asset.name if asset else asset_id

    return Concentration(
        hhi=hhi,
        effective_positions=(1 / hhi) if hhi else 0.0,
        top=[(a, label(a), w) for a, w in ranked[:top_n]],
        breaches=[(a, label(a), w) for a, w in ranked if w > limit],
    )


def rebalance_plan(
    report: DriftReport, *, threshold: float = 0.05, respect_bands: bool = True
) -> list[dict[str, Any]]:
    """Turn drift into the minimum set of moves that restores the policy.

    Moves back to the *edge of the band*, not to the target, when bands are
    respected. Trading to the midpoint costs more and buys nothing: the policy
    already said anywhere in the band is acceptable.
    """
    moves: list[dict[str, Any]] = []
    for drift in report.drifts:
        if respect_bands:
            if drift.in_band:
                continue
            edge = drift.lower if drift.actual < drift.lower else drift.upper
            delta = (edge - drift.actual) * report.total
        else:
            if abs(drift.gap) < threshold:
                continue
            delta = drift.rupees_to_target(report.total)
        if abs(delta) < 1:
            continue
        moves.append({
            "asset_class": drift.asset_class.value,
            "direction": "add" if delta > 0 else "trim",
            "amount": round(abs(delta), 2),
            "from_weight": round(drift.actual, 6),
            "to_weight": round(drift.actual + delta / report.total if report.total else 0.0, 6),
        })
    return sorted(moves, key=lambda m: m["amount"], reverse=True)


#: Instruments that can be turned into spendable money within a few days
#: without a loss that matters. Short-duration debt is deliberately excluded:
#: it is usually accessible, but "usually" is not what an emergency fund is.
from ..domain import AssetType  # noqa: E402

LIQUID_TYPES = {AssetType.LIQUID_FUND, AssetType.SAVINGS}


def liquid_value(portfolio: Portfolio) -> float:
    """Cash plus genuinely liquid instruments.

    The single source of truth for liquidity across the product. Before this
    existed, the suitability gate read a self-reported reserve while the
    cash-drag rule read the actual cash balance, and the two could disagree --
    which is how a user gets told to build a reserve and deploy their cash in
    the same breath.
    """
    total = as_float(portfolio.cash)
    for holding in portfolio.holdings:
        asset = portfolio.assets.get(holding.asset_id)
        if asset is not None and asset.asset_type in LIQUID_TYPES:
            total += as_float(holding.market_value)
    return total


def liquid_months(portfolio: Portfolio, monthly_expenses: float) -> float | None:
    """Months of expenses the liquid assets cover. ``None`` when expenses are
    unknown, so callers cannot mistake "no data" for "no cover"."""
    if monthly_expenses <= 0:
        return None
    return liquid_value(portfolio) / monthly_expenses
