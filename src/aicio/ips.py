"""The Investment Policy Statement.

A private bank writes the policy before it picks anything, and then every
later decision is checked against it. That order matters here for a specific
reason: it is what stops the system from rationalising whatever it happens to
find in the portfolio. The IPS is generated from Financial DNA, shown to the
user, editable by them, and versioned -- and after that, the decision engine
is only allowed to propose actions the policy permits.

Nothing in this module is a recommendation. It answers "what should this
person's portfolio look like", never "what should they buy".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from .domain import (
    AssetClass, FinancialProfile, Goal, LOCKED_TYPES, Portfolio, new_id,
)
from .money import as_float, money
from .provenance import Provenance, SourceKind, utcnow


#: Equity share by effective risk score (1-10) for a long horizon.
#: Deliberately conservative at the bottom and capped below 100% at the top:
#: a 10/10 investor still needs something to sell in a crash that is not the
#: thing that just fell.
_EQUITY_BY_RISK = {1: 0.10, 2: 0.20, 3: 0.30, 4: 0.40, 5: 0.50,
                   6: 0.60, 7: 0.68, 8: 0.75, 9: 0.82, 10: 0.88}

#: Horizon multiplier applied to the equity share. Money needed inside three
#: years does not belong in equity however brave the owner feels.
_HORIZON_FACTOR = [(2, 0.15), (3, 0.35), (5, 0.60), (7, 0.80), (10, 0.92), (99, 1.0)]


@dataclass(frozen=True)
class AllocationBand:
    """A target with a tolerance, because a point target is unmanageable.

    Rebalancing to an exact number generates trades, costs and tax for noise.
    A band says when drift stops being noise and becomes a decision.
    """

    asset_class: AssetClass
    target: float
    lower: float
    upper: float

    def breach(self, actual: float) -> float:
        """Signed distance outside the band, 0 inside it."""
        if actual < self.lower:
            return actual - self.lower
        if actual > self.upper:
            return actual - self.upper
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_class": self.asset_class.value,
            "target": round(self.target, 4),
            "lower": round(self.lower, 4),
            "upper": round(self.upper, 4),
        }


@dataclass
class Constraint:
    """A rule the engine must not propose an action against."""

    id: str
    description: str
    kind: str                      # concentration | sector | liquidity | exclusion | lockin
    limit: float | None = None
    subjects: tuple[str, ...] = ()
    hard: bool = True              # hard constraints block; soft ones warn

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "description": self.description, "kind": self.kind,
            "limit": self.limit, "subjects": list(self.subjects), "hard": self.hard,
        }


@dataclass
class InvestmentPolicy:
    """The generated, user-editable policy."""

    id: str
    user_id: str
    bands: list[AllocationBand]
    constraints: list[Constraint]
    objective: str
    horizon_years: int
    review_frequency_months: int = 6
    rebalance_threshold: float = 0.05
    min_emergency_months: int = 6
    version: int = 1
    created_at: datetime = field(default_factory=utcnow)
    edited_by_user: bool = False
    notes: list[str] = field(default_factory=list)

    def band(self, asset_class: AssetClass) -> AllocationBand | None:
        for item in self.bands:
            if item.asset_class == asset_class:
                return item
        return None

    def target(self, asset_class: AssetClass) -> float:
        band = self.band(asset_class)
        return band.target if band else 0.0

    @property
    def max_single_holding(self) -> float:
        for constraint in self.constraints:
            if constraint.kind == "concentration" and constraint.limit is not None:
                return constraint.limit
        return 0.10

    @property
    def max_sector(self) -> float:
        for constraint in self.constraints:
            if constraint.kind == "sector" and constraint.limit is not None:
                return constraint.limit
        return 0.30

    @property
    def excluded_sectors(self) -> tuple[str, ...]:
        for constraint in self.constraints:
            if constraint.kind == "exclusion":
                return constraint.subjects
        return ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "objective": self.objective,
            "horizon_years": self.horizon_years,
            "review_frequency_months": self.review_frequency_months,
            "rebalance_threshold": self.rebalance_threshold,
            "min_emergency_months": self.min_emergency_months,
            "version": self.version,
            "edited_by_user": self.edited_by_user,
            "bands": [b.to_dict() for b in self.bands],
            "constraints": [c.to_dict() for c in self.constraints],
            "notes": list(self.notes),
            "created_at": self.created_at.isoformat(),
        }

    def render(self) -> str:
        lines = [
            f"INVESTMENT POLICY STATEMENT  (v{self.version})",
            f"Objective: {self.objective}",
            f"Horizon: {self.horizon_years} years · review every {self.review_frequency_months} months",
            "",
            "Target allocation",
        ]
        for band in self.bands:
            lines.append(
                f"  {band.asset_class.value:<12} {band.target * 100:5.1f}%"
                f"   band {band.lower * 100:.0f}-{band.upper * 100:.0f}%"
            )
        lines += ["", "Constraints"]
        for constraint in self.constraints:
            mark = "must" if constraint.hard else "should"
            lines.append(f"  [{constraint.kind}] {mark}: {constraint.description}")
        if self.notes:
            lines += ["", "Notes"] + [f"  - {n}" for n in self.notes]
        return "\n".join(lines)


def horizon_factor(years: float) -> float:
    for cutoff, factor in _HORIZON_FACTOR:
        if years <= cutoff:
            return factor
    return 1.0


def generate_policy(
    profile: FinancialProfile,
    goals: Iterable[Goal] = (),
    *,
    today: date | None = None,
) -> InvestmentPolicy:
    """Derive a policy from Financial DNA.

    The shape of the output is driven by three inputs in order: how much risk
    the person can actually carry, how long the money has, and how much of it
    is already promised to something near-term.
    """
    goals = list(goals)
    today = today or date.today()
    notes: list[str] = []

    risk = profile.effective_risk
    equity = _EQUITY_BY_RISK[risk]

    horizon = float(profile.horizon_years)
    important = [g for g in goals if g.priority <= 2]
    if important:
        # Weighted by target size, not by which goal comes first. Letting the
        # earliest goal set the horizon de-risks retirement money because of a
        # school fee eight years out, which is the wrong answer by an order of
        # magnitude when retirement is twenty times the size.
        weight_total = sum(as_float(g.target_amount) for g in important)
        if weight_total > 0:
            weighted = sum(
                as_float(g.target_amount) * g.years_remaining(today=today) for g in important
            ) / weight_total
        else:
            weighted = horizon
        soonest = min(g.years_remaining(today=today) for g in important if not g.flexible) \
            if any(not g.flexible for g in important) else weighted
        # A fixed near-term goal still pulls the horizon in, just not all the way.
        horizon = min(horizon, max(2.0, (weighted + soonest) / 2 if soonest < weighted else weighted))
    equity *= horizon_factor(horizon)

    if profile.risk_gap >= 3:
        notes.append(
            "Stated risk tolerance exceeds measured risk capacity by "
            f"{profile.risk_gap} points; policy follows capacity, which is the "
            "lower of the two."
        )
    if profile.income_stability == "concentrated":
        equity *= 0.9
        notes.append("Income is concentrated, so equity is trimmed to avoid "
                     "correlating career risk with portfolio risk.")

    equity = round(min(0.88, max(0.05, equity)), 2)

    gold = 0.05 if equity >= 0.35 else 0.03
    cash = 0.05
    debt = round(max(0.05, 1.0 - equity - gold - cash), 2)
    # Absorb rounding drift into debt so the targets always sum to 1.
    debt = round(debt + (1.0 - (equity + gold + cash + debt)), 4)

    def band(asset_class: AssetClass, target: float, width: float) -> AllocationBand:
        return AllocationBand(
            asset_class,
            round(target, 4),
            round(max(0.0, target - width), 4),
            round(min(1.0, target + width), 4),
        )

    bands = [
        band(AssetClass.EQUITY, equity, 0.07),
        band(AssetClass.DEBT, debt, 0.07),
        band(AssetClass.GOLD, gold, 0.03),
        band(AssetClass.CASH, cash, 0.05),
    ]

    constraints = [
        Constraint(
            id=new_id("con", profile.user_id, "concentration"),
            description=(
                f"No single holding above {profile.max_single_holding_pct:.0%} of "
                "portfolio value, measured look-through"
            ),
            kind="concentration",
            limit=profile.max_single_holding_pct,
        ),
        Constraint(
            id=new_id("con", profile.user_id, "sector"),
            description=f"No sector above {profile.max_sector_pct:.0%} look-through exposure",
            kind="sector",
            limit=profile.max_sector_pct,
        ),
        Constraint(
            id=new_id("con", profile.user_id, "liquidity"),
            description=(
                f"Keep {profile.liquidity_need_months} months of expenses in cash or "
                "liquid instruments before adding risk assets"
            ),
            kind="liquidity",
            limit=float(profile.liquidity_need_months),
        ),
    ]
    if profile.excluded_sectors:
        constraints.append(Constraint(
            id=new_id("con", profile.user_id, "exclusion"),
            description="Excluded sectors: " + ", ".join(profile.excluded_sectors),
            kind="exclusion",
            subjects=tuple(profile.excluded_sectors),
        ))
    constraints.append(Constraint(
        id=new_id("con", profile.user_id, "lockin"),
        description="Do not propose exits from instruments inside a statutory lock-in",
        kind="lockin",
        subjects=tuple(t.value for t in LOCKED_TYPES),
    ))

    objective = _objective(profile, goals)
    return InvestmentPolicy(
        id=new_id("ips", profile.user_id, risk, round(equity, 2)),
        user_id=profile.user_id,
        bands=bands,
        constraints=constraints,
        objective=objective,
        horizon_years=int(round(horizon)),
        min_emergency_months=profile.liquidity_need_months,
        notes=notes,
    )


def _objective(profile: FinancialProfile, goals: list[Goal]) -> str:
    if goals:
        primary = sorted(goals, key=lambda g: (g.priority, g.target_date))[0]
        return (
            f"Fund '{primary.name}' by {primary.target_date.isoformat()} while keeping "
            f"drawdown within what a risk-capacity score of {profile.risk_capacity}/10 "
            "can absorb"
        )
    return (
        "Grow real wealth at a pace consistent with a risk capacity of "
        f"{profile.risk_capacity}/10, without forcing a sale in a downturn"
    )


# ---------------------------------------------------------------------------
# Suitability
# ---------------------------------------------------------------------------

@dataclass
class SuitabilityVerdict:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reasons": self.reasons, "warnings": self.warnings}


def check_suitability(
    policy: InvestmentPolicy,
    profile: FinancialProfile,
    portfolio: Portfolio,
    *,
    action: str,
    asset_id: str = "",
    amount: Decimal | None = None,
    builds_liquidity: bool = False,
) -> SuitabilityVerdict:
    """The gate every material action passes before a user ever sees it.

    Hard constraints block. Soft ones attach a warning that the explanation
    layer is required to surface -- silently downgrading a warning would be
    the same failure as not having the check.

    ``builds_liquidity`` marks a purchase that *is* the reserve being built.
    Without it the liquidity rule would block itself: the gate would refuse
    "put money into a liquid fund" on the grounds that liquidity is short,
    which is the one piece of advice a user in that position needs.
    """
    from .engine.allocation import LIQUID_TYPES, liquid_months

    reasons: list[str] = []
    warnings: list[str] = []

    asset = portfolio.assets.get(asset_id) if asset_id else None
    into_liquid = builds_liquidity or (asset is not None and asset.asset_type in LIQUID_TYPES)

    if action in {"EXIT_SWITCH", "REDUCE"} and asset is not None and asset.lock_in:
        reasons.append(
            f"{asset.name} is inside a lock-in ({asset.lock_in}); an exit cannot be executed"
        )

    if action == "BUY_INCREASE" and not into_liquid:
        covered = liquid_months(portfolio, as_float(profile.annual_expenses) / 12)
        if covered is not None and covered < policy.min_emergency_months:
            reasons.append(
                f"Liquid assets cover {covered:.1f} months of expenses against a policy "
                f"minimum of {policy.min_emergency_months}; build the reserve before "
                "adding risk assets"
            )

    if action == "BUY_INCREASE":
        if asset is not None and asset.sector and asset.sector in policy.excluded_sectors:
            reasons.append(f"{asset.sector} is an excluded sector in this policy")
        if asset is not None and amount is not None:
            value = as_float(portfolio.market_value)
            if value > 0:
                existing = sum(as_float(h.market_value) for h in portfolio.holdings_of(asset_id))
                after = (existing + as_float(amount)) / (value + as_float(amount))
                if after > policy.max_single_holding:
                    reasons.append(
                        f"Adding {money(amount)} would take {asset.name} to "
                        f"{after:.1%} of the portfolio, above the "
                        f"{policy.max_single_holding:.0%} single-holding limit"
                    )

    if action in {"BUY_INCREASE", "REDUCE", "EXIT_SWITCH"} and profile.risk_gap >= 3:
        warnings.append(
            "Stated risk tolerance is materially above measured capacity; this "
            "action is sized to capacity, not to appetite"
        )

    if portfolio.stale_holdings():
        warnings.append(
            f"{len(portfolio.stale_holdings())} holding(s) have not been refreshed "
            "recently; figures may be out of date"
        )

    return SuitabilityVerdict(allowed=not reasons, reasons=reasons, warnings=warnings)


def policy_provenance(policy: InvestmentPolicy) -> Provenance:
    return Provenance(
        kind=SourceKind.USER_INPUT,
        provider="aicio.ips",
        observed_at=policy.created_at,
        reference=policy.id,
        transformation="generated from Financial DNA" if not policy.edited_by_user else "user-edited",
        confidence=1.0 if policy.edited_by_user else 0.9,
    )
