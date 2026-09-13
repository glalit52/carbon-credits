"""The SIP optimiser.

The central idea, and the reason this module exists separately from
rebalancing: **redirect the next rupee before moving the last one**. A
portfolio that is 8 points overweight equity can be brought back by selling --
which triggers tax, costs exit loads and takes a decision away from the user --
or by pointing the next several months of contributions at what is underweight,
which costs nothing and happens automatically.

Selling is proposed only when future flows cannot close the gap in a
reasonable time, and the module says how long the flow-only route would take so
the user can judge the trade for themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from ..domain import AssetClass, Portfolio, SIP
from ..ips import InvestmentPolicy
from ..money import ZERO, as_float, money
from .allocation import AllocationBreakdown, DriftReport

#: Beyond this many months, "just redirect the SIPs" stops being a real answer
#: and a rebalancing trade has to be on the table.
FLOW_ONLY_PATIENCE_MONTHS = 24


@dataclass
class SIPChange:
    sip_id: str
    asset_id: str
    asset_label: str
    current_amount: Decimal
    proposed_amount: Decimal
    reason: str

    @property
    def delta(self) -> Decimal:
        return money(self.proposed_amount - self.current_amount)

    @property
    def verdict(self) -> str:
        if self.proposed_amount == ZERO:
            return "stop"
        if self.delta > 0:
            return "increase"
        if self.delta < 0:
            return "reduce"
        return "continue"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sip_id": self.sip_id, "asset_id": self.asset_id, "asset_label": self.asset_label,
            "current_amount": str(self.current_amount),
            "proposed_amount": str(self.proposed_amount),
            "delta": str(self.delta), "verdict": self.verdict, "reason": self.reason,
        }


@dataclass
class SIPPlan:
    monthly_total: Decimal
    changes: list[SIPChange]
    new_allocations: list[dict[str, Any]] = field(default_factory=list)
    months_to_close_gap: float | None = None
    requires_sale: bool = False
    sale_rationale: str = ""
    projected_weights: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> list[SIPChange]:
        return [c for c in self.changes if c.delta != ZERO]

    def to_dict(self) -> dict[str, Any]:
        return {
            "monthly_total": str(self.monthly_total),
            "changes": [c.to_dict() for c in self.changes],
            "new_allocations": self.new_allocations,
            "months_to_close_gap": (
                None if self.months_to_close_gap is None else round(self.months_to_close_gap, 1)
            ),
            "requires_sale": self.requires_sale,
            "sale_rationale": self.sale_rationale,
            "projected_weights": {k: round(v, 6) for k, v in self.projected_weights.items()},
            "notes": list(self.notes),
        }


def _class_of(portfolio: Portfolio, asset_id: str) -> AssetClass:
    asset = portfolio.assets.get(asset_id)
    return asset.asset_class if asset else AssetClass.OTHER


def _label(portfolio: Portfolio, asset_id: str) -> str:
    asset = portfolio.assets.get(asset_id)
    return asset.name if asset else asset_id


def months_to_close(
    gap_value: float, monthly_flow: float, *, growth_monthly: float = 0.0
) -> float | None:
    """How long redirecting the whole monthly flow would take to close a gap.

    ``None`` when the flow cannot close it at all, which is the honest answer
    when a ₹40 lakh overweight meets a ₹25,000 SIP.
    """
    if gap_value <= 0:
        return 0.0
    if monthly_flow <= 0:
        return None
    months = gap_value / monthly_flow
    return months if months <= 600 else None


def optimise_sips(
    portfolio: Portfolio,
    policy: InvestmentPolicy,
    breakdown: AllocationBreakdown,
    drift: DriftReport,
    *,
    additional_monthly: Decimal = ZERO,
    today: date,
) -> SIPPlan:
    """Re-point existing contributions at what the policy is short of.

    ``today`` is required rather than defaulted, for the same reason as in
    :func:`aicio.engine.goals.project_goal`: nothing in this package may read
    the clock, or the result stops being reproducible.
    """
    sips = portfolio.active_sips()
    current_monthly = as_float(portfolio.monthly_sip_total) + as_float(additional_monthly)
    notes: list[str] = []

    if current_monthly <= 0:
        return SIPPlan(
            monthly_total=ZERO,
            changes=[],
            notes=["No active contributions to redirect; a rebalance would have to "
                   "come from existing holdings."],
        )

    under = sorted(
        (d for d in drift.drifts if d.gap < 0),
        key=lambda d: d.gap,
    )
    over = sorted((d for d in drift.drifts if d.gap > 0), key=lambda d: -d.gap)

    if not under:
        changes = [
            SIPChange(sip.id, sip.asset_id, _label(portfolio, sip.asset_id),
                      sip.amount, sip.amount,
                      "Allocation is within policy; no redirection needed")
            for sip in sips
        ]
        return SIPPlan(
            monthly_total=money(current_monthly),
            changes=changes,
            months_to_close_gap=0.0,
            notes=["Contributions are already pointed at the right classes."],
        )

    # Split the monthly flow across underweight classes in proportion to how
    # far short each one is.
    shortfall = {d.asset_class: -d.gap * drift.total for d in under}
    total_short = sum(shortfall.values())
    allocations = {
        asset_class: current_monthly * (value / total_short)
        for asset_class, value in shortfall.items()
    } if total_short else {}

    changes: list[SIPChange] = []
    #: Contributions already going to an underweight class keep going there;
    #: only the ones feeding an overweight class get moved. Churning a SIP that
    #: is already correct costs the user a mandate change for nothing.
    for sip in sips:
        asset_class = _class_of(portfolio, sip.asset_id)
        if asset_class in shortfall:
            changes.append(SIPChange(
                sip.id, sip.asset_id, _label(portfolio, sip.asset_id),
                sip.amount, sip.amount,
                f"Already feeding {asset_class.value}, which is underweight",
            ))
            allocations[asset_class] = max(
                0.0, allocations.get(asset_class, 0.0) - as_float(sip.amount) / _per_month(sip)
            )
        else:
            over_label = asset_class.value
            changes.append(SIPChange(
                sip.id, sip.asset_id, _label(portfolio, sip.asset_id),
                sip.amount, ZERO,
                f"Redirect: {over_label} is at or above its policy band, so new money "
                "should go elsewhere rather than deepen the overweight",
            ))

    new_allocations = [
        {
            "asset_class": asset_class.value,
            "monthly_amount": round(amount, 2),
            "reason": f"{asset_class.value} is {abs(next(d.gap for d in under if d.asset_class == asset_class)):.1%} "
                      "below its policy target",
        }
        for asset_class, amount in sorted(allocations.items(), key=lambda kv: -kv[1])
        if amount >= 500
    ]

    # The gap that matters is the money needed to lift every underweight class
    # back into its band -- that is what the redirected contributions actually
    # buy. Measuring the overweight side instead answers a different question
    # (how long until the excess is diluted) and gives a much smaller number,
    # which reads as over-optimistic next to the allocation table.
    worst = max(over, key=lambda d: d.breach, default=None)
    gap_value = sum(max(0.0, d.lower - d.actual) * drift.total for d in under)
    months = months_to_close(gap_value, current_monthly)
    requires_sale = months is None or months > FLOW_ONLY_PATIENCE_MONTHS
    rationale = ""
    if requires_sale:
        subject = worst.asset_class.value if worst is not None else "the overweight class"
        rationale = (
            f"Bringing the underweight classes back into band needs {money(gap_value)}. "
            f"Contributions of {money(current_monthly)}/month would take "
            + (f"{months:.0f} months" if months else "longer than 50 years")
            + f" to get there, so trimming {subject} is worth considering alongside "
            "redirection."
        )
        notes.append(rationale)
    elif months:
        notes.append(
            f"Redirecting contributions closes the gap in about {months:.0f} months "
            "without selling anything or triggering tax."
        )

    projected = _project_weights(breakdown, allocations, months=min(12.0, months or 12.0))
    return SIPPlan(
        monthly_total=money(current_monthly),
        changes=changes,
        new_allocations=new_allocations,
        months_to_close_gap=months,
        requires_sale=requires_sale,
        sale_rationale=rationale,
        projected_weights=projected,
        notes=notes,
    )


def _per_month(sip: SIP) -> float:
    from ..domain import PER_YEAR
    per_year = PER_YEAR[sip.frequency]
    return 12 / per_year if per_year else 1.0


def _project_weights(
    breakdown: AllocationBreakdown, allocations: dict[AssetClass, float], *, months: float
) -> dict[str, float]:
    """Where the allocation lands if the plan runs for ``months``, holding
    prices flat. Flat prices on purpose: mixing a market forecast into a
    contribution plan would make the plan impossible to check."""
    projected = dict(breakdown.by_class)
    for asset_class, monthly in allocations.items():
        projected[asset_class] = projected.get(asset_class, 0.0) + monthly * months
    total = sum(projected.values())
    if total <= 0:
        return {}
    return {k.value: v / total for k, v in projected.items()}
