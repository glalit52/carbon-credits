"""One deterministic pass over a portfolio.

Everything downstream -- the decision engine, the alerts, the reports and the
AI banker -- reads from a single :class:`PortfolioAnalysis` produced here.
That is a deliberate constraint rather than convenience:

*   The chat, the dashboard and the recommendation cannot disagree about a
    number, because there is only one place the number is computed.
*   The AI layer is handed a :class:`~aicio.provenance.FactSheet` built from
    the same pass, so "what the model knows" and "what the engine computed"
    are the same set by construction.
*   The whole analysis is a pure function of (portfolio, profile, policy,
    goals, market snapshot), so it re-runs identically months later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Sequence

from .domain import (
    AssetClass, FinancialProfile, Goal, Holding, Portfolio, TaxLot, Transaction,
)
from .engine.allocation import (
    AllocationBreakdown, Concentration, DriftReport, allocation_breakdown,
    concentration, drift_report, liquid_months, liquid_value, rebalance_plan,
)
from .engine.goals import (
    CapitalMarketAssumptions, DEFAULT_CMA, GoalProjection, project_goal,
)
from .engine.health import HealthScore, health_score
from .engine.returns import CashFlow, ReturnError, absolute_return, xirr
from .engine.risk import ScenarioResult, Shock, STANDARD_SHOCKS, run_scenarios
from .engine.sip import SIPPlan, optimise_sips
from .engine.taxlots import (
    GainType, INDIA_FY2526, TaxRules, TaxSummary, UnrealisedPosition, build_lots,
    realised_gains, tax_summary, unrealised_gains,
)
from .engine.xray import (
    Overlap, SingleName, XRay, look_through, overlapping_pairs, single_name_breaches,
)
from .ips import InvestmentPolicy
from .money import ZERO, as_float, money
from .provenance import (
    Fact, FactSheet, Provenance, SourceKind, assumption, utcnow,
)
from . import ENGINE_VERSION


@dataclass
class HoldingView:
    """One position with everything the product knows about it."""

    holding: Holding
    label: str
    asset_class: AssetClass
    weight: float
    market_value: float
    invested: float
    gain: float
    gain_pct: float
    quality: float | None = None
    lots: list[TaxLot] = field(default_factory=list)
    unrealised: list[UnrealisedPosition] = field(default_factory=list)
    xirr: float | None = None
    locked: str = ""
    stale: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.holding.asset_id,
            "account_id": self.holding.account_id,
            "label": self.label,
            "asset_class": self.asset_class.value,
            "units": str(self.holding.units),
            "price": str(self.holding.current_price),
            "weight": round(self.weight, 6),
            "market_value": round(self.market_value, 2),
            "invested": round(self.invested, 2),
            "gain": round(self.gain, 2),
            "gain_pct": round(self.gain_pct, 6),
            "quality": None if self.quality is None else round(self.quality, 1),
            "xirr": None if self.xirr is None else round(self.xirr, 6),
            "locked": self.locked,
            "stale": self.stale,
            "short_term_units": str(sum(
                (p.units for p in self.unrealised if p.gain_type == GainType.SHORT_TERM),
                start=Decimal("0"),
            )),
        }


@dataclass
class PortfolioAnalysis:
    """The complete deterministic picture at one instant."""

    user_id: str
    as_of: date
    portfolio: Portfolio
    policy: InvestmentPolicy
    profile: FinancialProfile
    breakdown: AllocationBreakdown
    drift: DriftReport
    concentration: Concentration
    xray: XRay
    overlaps: list[Overlap]
    #: Companies above the policy's single-name limit once funds are opened up.
    single_names: list[SingleName]
    holdings: list[HoldingView]
    health: HealthScore
    scenarios: list[ScenarioResult]
    projections: list[GoalProjection]
    tax: TaxSummary
    sip_plan: SIPPlan
    rebalance: list[dict[str, Any]]
    facts: FactSheet
    portfolio_xirr: float | None = None
    #: Months of expenses covered by cash and genuinely liquid instruments.
    #: ``None`` when expenses are unknown -- never silently zero.
    liquid_months: float | None = None
    engine_version: str = ENGINE_VERSION
    fingerprint: str = ""
    generated_at: datetime = field(default_factory=utcnow)

    def holding(self, asset_id: str) -> HoldingView | None:
        for view in self.holdings:
            if view.holding.asset_id == asset_id:
                return view
        return None

    @property
    def net_worth(self) -> float:
        return as_float(self.portfolio.net_worth)

    @property
    def monthly_expenses(self) -> float:
        return as_float(self.profile.annual_expenses) / 12

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "as_of": self.as_of.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "engine_version": self.engine_version,
            "fingerprint": self.fingerprint,
            "net_worth": round(self.net_worth, 2),
            "market_value": round(as_float(self.portfolio.market_value), 2),
            "invested": round(as_float(self.portfolio.invested), 2),
            "cash": round(as_float(self.portfolio.cash), 2),
            "unrealised_gain": round(as_float(self.portfolio.unrealised_gain), 2),
            "portfolio_xirr": (
                None if self.portfolio_xirr is None else round(self.portfolio_xirr, 6)
            ),
            "liquid_months": (
                None if self.liquid_months is None else round(self.liquid_months, 2)
            ),
            "health": self.health.to_dict(),
            "allocation": self.breakdown.to_dict(),
            "drift": self.drift.to_dict(),
            "concentration": self.concentration.to_dict(),
            "xray": self.xray.to_dict(),
            "overlaps": [o.to_dict() for o in self.overlaps],
            "single_names": [s.to_dict() for s in self.single_names],
            "holdings": [h.to_dict() for h in self.holdings],
            "scenarios": [s.to_dict() for s in self.scenarios],
            "projections": [p.to_dict() for p in self.projections],
            "tax": self.tax.to_dict(),
            "sip_plan": self.sip_plan.to_dict(),
            "rebalance": self.rebalance,
            "policy": self.policy.to_dict(),
            "facts": self.facts.to_dict(),
        }


def analyse(
    portfolio: Portfolio,
    profile: FinancialProfile,
    policy: InvestmentPolicy,
    goals: Sequence[Goal] = (),
    *,
    today: date | None = None,
    tax_rules: TaxRules = INDIA_FY2526,
    cma: CapitalMarketAssumptions = DEFAULT_CMA,
    shocks: Sequence[Shock] = STANDARD_SHOCKS,
    quality: dict[str, float] | None = None,
    behaviour: dict[str, float] | None = None,
    monte_carlo_trials: int = 2000,
) -> PortfolioAnalysis:
    """Run the full deterministic analysis."""
    today = today or portfolio.as_of
    facts = FactSheet(subject=f"Portfolio analysis for {portfolio.user_id} on {today.isoformat()}")
    engine_source = Provenance(
        kind=SourceKind.DERIVED, provider="aicio.engine",
        observed_at=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
        transformation=ENGINE_VERSION, confidence=1.0,
    )

    breakdown = allocation_breakdown(portfolio)
    drift = drift_report(breakdown, policy)
    conc = concentration(portfolio)
    xray = look_through(portfolio)
    overlaps = overlapping_pairs(portfolio)
    single_names = single_name_breaches(xray, limit=policy.max_single_holding)

    total_value = as_float(portfolio.market_value) + as_float(portfolio.cash)
    views = _holding_views(portfolio, total_value, today, tax_rules, quality or {})

    all_unrealised = [item for view in views for item in view.unrealised]
    all_realised = []
    for asset_id in {h.asset_id for h in portfolio.holdings}:
        transactions = portfolio.transactions_for(asset_id)
        if transactions:
            all_realised.extend(realised_gains(transactions, portfolio.asset(asset_id), rules=tax_rules))
    tax = tax_summary(
        all_realised, all_unrealised,
        marginal_rate=profile.marginal_tax_rate, rules=tax_rules,
    )

    exposure = {k.value: v for k, v in breakdown.by_class.items()}
    scenarios = run_scenarios(
        exposure, monthly_expenses=as_float(profile.annual_expenses) / 12, shocks=shocks
    )

    weights = {k: v for k, v in breakdown.weights.items()}
    projections = [
        project_goal(
            goal,
            current_value=_goal_funding(goal, portfolio, total_value),
            monthly_contribution=_goal_contribution(goal, portfolio),
            weights=weights, today=today, cma=cma, trials=monte_carlo_trials,
        )
        for goal in sorted(goals, key=lambda g: (g.priority, g.target_date))
    ]

    sip_plan = optimise_sips(portfolio, policy, breakdown, drift, today=today)

    short_term_value = sum(
        as_float(p.gain) for p in all_unrealised
        if p.gain_type == GainType.SHORT_TERM and p.gain > 0
    )
    total_gain = sum(as_float(p.gain) for p in all_unrealised if p.gain > 0)
    short_share = (short_term_value / total_gain) if total_gain > 0 else None

    stale_share = (
        len(portfolio.stale_holdings()) / len(portfolio.holdings) if portfolio.holdings else 0.0
    )
    monthly_expenses = as_float(profile.annual_expenses) / 12
    cover = liquid_months(portfolio, monthly_expenses)
    overlap_exposure = 0.0
    if overlaps:
        worst = overlaps[0]
        overlap_exposure = sum(
            view.weight for view in views
            if view.holding.asset_id in {worst.left_id, worst.right_id}
        )
    health = health_score(
        breakdown=breakdown, drift=drift, concentration_=conc, xray=xray, overlaps=overlaps,
        overlap_exposure=overlap_exposure,
        projections=projections,
        emergency_months=cover,
        required_emergency_months=policy.min_emergency_months,
        unrealised_short_term_share=short_share,
        stale_holding_share=stale_share,
        quality_scores=[v.quality for v in views if v.quality is not None],
        behaviour=behaviour,
        max_single_holding=policy.max_single_holding,
        single_name_top=single_names[0].weight if single_names else (
            xray.by_company[0].weight if xray.by_company else 0.0),
        max_sector=policy.max_sector,
    )

    portfolio_xirr = _portfolio_xirr(portfolio, today)

    # ---- the grounded fact sheet ----------------------------------------
    facts.record("net_worth", round(as_float(portfolio.net_worth), 2), "INR", engine_source)
    facts.record("market_value", round(as_float(portfolio.market_value), 2), "INR", engine_source)
    facts.record("invested", round(as_float(portfolio.invested), 2), "INR", engine_source)
    facts.record("cash", round(as_float(portfolio.cash), 2), "INR", engine_source)
    facts.record(
        "unrealised_gain_pct",
        round(absolute_return(portfolio.invested, portfolio.market_value), 6),
        "fraction", engine_source,
    )
    if portfolio_xirr is not None:
        facts.record("portfolio_xirr", round(portfolio_xirr, 6), "fraction/yr", engine_source,
                     "money-weighted, from all recorded cash flows")
    else:
        facts.note("Portfolio XIRR is unavailable: transaction history is incomplete.")

    facts.record("health_score", health.score, "0-100", engine_source, health.band)
    for dimension in health.dimensions:
        if dimension.score is not None:
            facts.record(f"health.{dimension.key}", round(dimension.score, 1), "0-100",
                         engine_source, dimension.summary)
    for key in health.unassessed:
        facts.note(f"Health dimension '{key}' could not be assessed with the data available.")

    for asset_class, weight in sorted(breakdown.weights.items(), key=lambda kv: -kv[1]):
        facts.record(f"allocation.{asset_class.value}", round(weight, 6), "fraction", engine_source)
    for item in drift.drifts:
        facts.record(
            f"drift.{item.asset_class.value}", round(item.gap, 6), "fraction", engine_source,
            f"target {item.target:.0%}, band {item.lower:.0%}-{item.upper:.0%}"
            + ("" if item.in_band else f", BREACH {item.breach:+.1%}"),
        )

    facts.record("concentration.hhi", round(conc.hhi, 6), "index", engine_source)
    facts.record("concentration.effective_positions", round(conc.effective_positions, 2),
                 "positions", engine_source)
    for asset_id, label, weight in conc.top[:5]:
        facts.record(f"position_weight.{asset_id}", round(weight, 6), "fraction",
                     engine_source, label)
    for name in single_names:
        facts.record(
            f"single_name.{name.key}", round(name.weight, 6), "fraction", engine_source,
            f"{name.label} through {len(name.through)} holding(s), above the "
            f"{policy.max_single_holding:.0%} limit",
        )
    if xray.by_company:
        top = xray.by_company[0]
        facts.record("lookthrough.top_company", round(top.weight, 6), "fraction",
                     engine_source, f"{top.label} across {len(top.contributors)} holdings")
    if xray.coverage < 1:
        facts.note(
            f"Look-through covers {xray.coverage:.0%} of portfolio value; the rest sits in "
            "funds whose constituent holdings we do not have."
        )
    for overlap in overlaps[:3]:
        facts.record(
            f"overlap.{overlap.left_id}.{overlap.right_id}", round(overlap.overlap, 4),
            "fraction", engine_source, f"{overlap.left_name} vs {overlap.right_name}",
        )

    if cover is not None:
        facts.record("liquid_months", round(cover, 2), "months", engine_source,
                     f"cash and liquid funds against a {policy.min_emergency_months}-month "
                     "policy minimum")
        facts.record("liquid_value", round(liquid_value(portfolio), 2), "INR", engine_source)
    for scenario in scenarios:
        facts.record(f"scenario.{scenario.name}", round(scenario.loss_pct, 6), "fraction",
                     engine_source, scenario.description)
    for projection in projections:
        facts.record(f"goal.{projection.goal_id}.probability", round(projection.probability, 4),
                     "probability", engine_source,
                     f"{projection.goal_name}: {projection.status}")
        facts.record(f"goal.{projection.goal_id}.required_monthly",
                     round(projection.required_monthly, 2), "INR/month", engine_source)

    facts.record("tax.estimated", as_float(tax.estimated_tax), "INR", engine_source,
                 "current financial year, realised gains only")
    facts.record("tax.ltcg_exemption_left", as_float(tax.ltcg_exemption_left), "INR",
                 engine_source)
    for note in tax.notes:
        facts.note(note)

    facts.add(Fact("capital_market_assumptions", cma.to_dict(), "assumptions",
                   assumption(cma.source)))
    if portfolio.stale_holdings():
        facts.note(
            f"{len(portfolio.stale_holdings())} of {len(portfolio.holdings)} holdings have "
            "not been refreshed inside their freshness window."
        )

    return PortfolioAnalysis(
        user_id=portfolio.user_id,
        as_of=today,
        portfolio=portfolio,
        policy=policy,
        profile=profile,
        breakdown=breakdown,
        drift=drift,
        concentration=conc,
        xray=xray,
        overlaps=overlaps,
        single_names=single_names,
        holdings=views,
        health=health,
        scenarios=scenarios,
        projections=projections,
        tax=tax,
        sip_plan=sip_plan,
        rebalance=rebalance_plan(drift, threshold=policy.rebalance_threshold),
        facts=facts,
        portfolio_xirr=portfolio_xirr,
        liquid_months=cover,
        fingerprint=portfolio.fingerprint(),
    )


def _holding_views(
    portfolio: Portfolio,
    total_value: float,
    today: date,
    tax_rules: TaxRules,
    quality: dict[str, float],
) -> list[HoldingView]:
    views: list[HoldingView] = []
    for holding in portfolio.holdings:
        asset = portfolio.asset(holding.asset_id)
        transactions = portfolio.transactions_for(holding.asset_id)
        lots = holding.lots
        if not lots and transactions:
            lots, _ = build_lots(transactions)
        positions = unrealised_gains(
            lots, asset, holding.current_price, on=today, rules=tax_rules
        ) if lots else []
        value = as_float(holding.market_value)
        views.append(HoldingView(
            holding=holding,
            label=asset.name,
            asset_class=asset.asset_class,
            weight=value / total_value if total_value else 0.0,
            market_value=value,
            invested=as_float(holding.invested),
            gain=as_float(holding.unrealised_gain),
            gain_pct=holding.unrealised_pct,
            quality=quality.get(holding.asset_id),
            lots=lots,
            unrealised=positions,
            xirr=_holding_xirr(transactions, holding, today),
            locked=asset.lock_in,
            stale=holding.provenance.is_stale(),
        ))
    return sorted(views, key=lambda v: v.market_value, reverse=True)


def _holding_xirr(
    transactions: Sequence[Transaction], holding: Holding, today: date
) -> float | None:
    if not transactions:
        return None
    flows = [CashFlow.of(t.trade_date, t.cash_flow) for t in transactions if t.cash_flow != ZERO]
    if not flows:
        return None
    # The position's current value is the terminal inflow: without it the IRR
    # would measure only what has been sold, which for a held position is
    # nothing at all.
    flows.append(CashFlow.of(today, holding.market_value))
    try:
        return xirr(flows)
    except ReturnError:
        return None


def _portfolio_xirr(portfolio: Portfolio, today: date) -> float | None:
    flows = [
        CashFlow.of(t.trade_date, t.cash_flow)
        for t in portfolio.transactions if t.cash_flow != ZERO
    ]
    if len(flows) < 2:
        return None
    flows.append(CashFlow.of(today, portfolio.market_value + portfolio.cash))
    try:
        return xirr(flows)
    except ReturnError:
        return None


def _goal_funding(goal: Goal, portfolio: Portfolio, total_value: float) -> float:
    """How much of the portfolio is already earmarked for this goal.

    Explicitly linked accounts when the user has said; otherwise the goal's own
    recorded funding. It deliberately does not spread the whole portfolio
    across goals by priority -- that would let one optimistic projection be
    counted twice.
    """
    if goal.linked_account_ids:
        return sum(
            as_float(h.market_value) for h in portfolio.holdings
            if h.account_id in goal.linked_account_ids
        )
    return as_float(goal.current_funding)


def _goal_contribution(goal: Goal, portfolio: Portfolio) -> float:
    linked = [s for s in portfolio.active_sips() if s.goal_id == goal.id]
    if linked:
        return sum(as_float(s.annual_amount) / 12 for s in linked)
    return as_float(goal.monthly_contribution)
