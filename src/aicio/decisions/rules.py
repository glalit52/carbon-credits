"""The rules.

Each one reads the deterministic analysis, decides whether a condition holds,
and produces a fully formed :class:`~aicio.domain.Recommendation` -- including
the case against itself. That last part is not decoration: a rule that cannot
articulate why it might be wrong is a rule that has not been thought through,
and the domain model refuses to accept a material action without it.

Ordering in this file runs from "protects the user" to "improves the user",
which is also the order the product wants to reason in: liquidity and data
integrity before allocation, allocation before optimisation, optimisation
before tax.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Iterator, Sequence

from .. import ENGINE_VERSION
from ..analysis import PortfolioAnalysis
from ..domain import (
    Action, AssetClass, Evidence, Priority, Recommendation, new_id,
)
from ..engine.taxlots import GainType, exit_tax_cost
from ..money import as_float, format_money, money
from .scoring import priority_for, score

Rule = Callable[["RuleContext"], Iterator[Recommendation]]
RULES: list[tuple[str, str, Rule]] = []


@dataclass
class RuleContext:
    """Everything a rule may look at. Nothing else is in scope."""

    analysis: PortfolioAnalysis
    today: date

    @property
    def portfolio(self):
        return self.analysis.portfolio

    @property
    def policy(self):
        return self.analysis.policy

    @property
    def profile(self):
        return self.analysis.profile

    @property
    def total(self) -> float:
        return as_float(self.portfolio.market_value) + as_float(self.portfolio.cash)

    def fact_ids(self, *names: str) -> tuple[str, ...]:
        out: list[str] = []
        for name in names:
            fact = self.analysis.facts.get(name)
            if fact is not None:
                out.append(fact.id)
        return tuple(out)

    def build(
        self,
        *,
        rule_id: str,
        action: Action,
        subject_id: str,
        subject_label: str,
        headline: str,
        reasons: Sequence[str],
        confidence: float,
        priority: Priority,
        evidence: Sequence[Evidence] = (),
        risks: Sequence[str] = (),
        counterarguments: Sequence[str] = (),
        alternatives: Sequence[str] = (),
        portfolio_impact: str = "",
        tax_impact: str = "",
        suggested_amount: Decimal | None = None,
        review_in_days: int = 90,
        goal_ids: Sequence[str] = (),
    ) -> Recommendation:
        return Recommendation(
            id=new_id("rec", self.analysis.user_id, rule_id, subject_id,
                      self.analysis.fingerprint),
            user_id=self.analysis.user_id,
            action=action,
            subject_id=subject_id,
            subject_label=subject_label,
            priority=priority,
            confidence=round(min(0.97, max(0.05, confidence)), 4),
            headline=headline,
            reasons=list(reasons),
            evidence=list(evidence),
            portfolio_impact=portfolio_impact,
            tax_impact=tax_impact,
            risks=list(risks),
            counterarguments=list(counterarguments),
            alternatives=list(alternatives),
            suggested_amount=suggested_amount,
            review_by=self.today + timedelta(days=review_in_days),
            expires_on=self.today + timedelta(days=max(30, review_in_days)),
            rule_id=rule_id,
            engine_version=ENGINE_VERSION,
            portfolio_fingerprint=self.analysis.fingerprint,
            goal_ids=tuple(goal_ids),
        )


def rule(rule_id: str, description: str) -> Callable[[Rule], Rule]:
    def wrap(fn: Rule) -> Rule:
        RULES.append((rule_id, description, fn))
        return fn
    return wrap


# ---------------------------------------------------------------------------
# Protection
# ---------------------------------------------------------------------------

@rule("R-DATA-ANOMALY", "Holdings that look implausible or duplicated")
def data_anomaly(ctx: RuleContext) -> Iterator[Recommendation]:
    """Fires before anything else. An analysis built on a bad import is worse
    than no analysis, and the user is the only one who can adjudicate."""
    suspicious: list[str] = []
    for view in ctx.analysis.holdings:
        if view.market_value <= 0:
            suspicious.append(f"{view.label}: non-positive market value")
        elif view.invested > 0 and view.gain_pct > 20:
            suspicious.append(
                f"{view.label}: a {view.gain_pct:.0%} gain suggests a wrong cost basis "
                "or a missed corporate action"
            )
    duplicates = [
        f"{left.label} and {right.label}"
        for index, left in enumerate(ctx.analysis.holdings)
        for right in ctx.analysis.holdings[index + 1:]
        if left.label == right.label and left.holding.account_id != right.holding.account_id
        and left.holding.units == right.holding.units
    ]
    if not suspicious and not duplicates:
        return
    reasons = suspicious[:4] + [f"Possible duplicate import: {d}" for d in duplicates[:3]]
    yield ctx.build(
        rule_id="R-DATA-ANOMALY", action=Action.REVIEW, subject_id="portfolio",
        subject_label="Imported data",
        headline="Some imported positions do not look right",
        reasons=reasons,
        confidence=0.6,
        priority=priority_for(0.0, safety_critical=True),
        evidence=[Evidence("Imported holdings", ctx.fact_ids("market_value"),
                           "Parsed from uploaded statements and connected accounts")],
        risks=["Every downstream number, including the health score, inherits an import error"],
        counterarguments=["A large gain can be genuine on a long-held position"],
        alternatives=["Correct the affected rows, or re-upload the source statement"],
        review_in_days=7,
    )


@rule("R-LIQUIDITY", "Emergency reserve below the policy minimum")
def liquidity_gap(ctx: RuleContext) -> Iterator[Recommendation]:
    profile, policy = ctx.profile, ctx.policy
    covered = ctx.analysis.liquid_months
    if covered is None:
        return
    required = policy.min_emergency_months
    if covered >= required:
        return
    monthly = as_float(profile.annual_expenses) / 12
    gap = money((required - covered) * monthly)
    severity = min(1.0, (required - covered) / max(1, required))
    value = score(impact=0.85, urgency=0.8, severity=severity, confidence=0.95,
                  goal_relevance=0.4).value
    yield ctx.build(
        rule_id="R-LIQUIDITY", action=Action.BUY_INCREASE, subject_id="cash",
        subject_label="Emergency reserve",
        headline=f"Build the emergency reserve to {required} months before adding market risk",
        reasons=[
            f"Liquid cover is {covered:.1f} months against a policy minimum of {required}.",
            f"Closing the gap needs about {format_money(gap)} in a liquid instrument.",
            "Without it, a job loss or medical event forces a sale at whatever price "
            "the market happens to be offering that week.",
        ],
        confidence=0.95,
        priority=Priority.CRITICAL if covered < required / 2 else priority_for(value),
        evidence=[Evidence(
            "Emergency cover", ctx.fact_ids("liquid_months", "liquid_value", "cash"),
            f"{covered:.1f} months covered, policy minimum {required}",
            "Financial DNA + holdings",
        )],
        portfolio_impact=f"Moves {format_money(gap)} of future contributions into liquid assets",
        tax_impact="None: this is new money, not a sale",
        risks=["Holding more cash reduces expected long-run return"],
        counterarguments=[
            "If income is highly stable and credit lines are available, a smaller "
            "reserve can be defensible",
        ],
        alternatives=[
            "Direct the next few months of SIP into a liquid or overnight fund",
            "Lower the policy's liquidity requirement if the current one is wrong for you",
        ],
        suggested_amount=gap,
        review_in_days=30,
    )


@rule("R-STALE-DATA", "Analysis resting on prices that are too old to act on")
def stale_data(ctx: RuleContext) -> Iterator[Recommendation]:
    stale = ctx.portfolio.stale_holdings()
    if not stale:
        return
    share = len(stale) / max(1, len(ctx.portfolio.holdings))
    if share < 0.2:
        return
    yield ctx.build(
        rule_id="R-STALE-DATA", action=Action.REVIEW, subject_id="portfolio",
        subject_label="Data freshness",
        headline=f"{len(stale)} holdings have not been refreshed recently",
        reasons=[
            f"{share:.0%} of positions are outside their freshness window, so valuations "
            "and every metric built on them are approximate.",
            "Recommendations that depend on these prices are being held back.",
        ],
        confidence=0.9,
        priority=Priority.MEDIUM if share < 0.5 else Priority.HIGH,
        evidence=[Evidence("Holding provenance", (),
                           f"{len(stale)} of {len(ctx.portfolio.holdings)} holdings stale")],
        risks=["Acting on stale prices can invert the decision"],
        counterarguments=["For illiquid or infrequently valued assets, some staleness is normal"],
        alternatives=["Reconnect the account, or upload a current statement"],
        review_in_days=14,
    )


# ---------------------------------------------------------------------------
# Allocation and concentration
# ---------------------------------------------------------------------------

@rule("R-ALLOC-DRIFT", "Asset allocation outside its policy band")
def allocation_drift(ctx: RuleContext) -> Iterator[Recommendation]:
    """Prefers redirecting contributions to selling wherever the arithmetic
    allows, which is the single most valuable behaviour in the product: it
    turns a taxable event into a free one.

    Emits at most one item. Drift is a single fact about the portfolio -- being
    overweight equity *is* being underweight debt -- and listing it once per
    asset class turns one decision into four and buries everything else.
    """
    # Cash drift is handled by the liquidity and cash-drag rules, which know
    # about the emergency reserve. Saying "trim cash" here without that
    # context is how a product tells someone to invest their safety net.
    breaches = [
        item for item in ctx.analysis.drift.breaches
        if item.asset_class != AssetClass.CASH
        and abs(item.breach) * ctx.analysis.drift.total >= 10000
    ]
    if breaches:
        worst = max(breaches, key=lambda item: abs(item.breach))
        counterparts = [item for item in breaches if item is not worst]
        for item in [worst]:
            gap_value = abs(item.breach) * ctx.analysis.drift.total
            overweight = item.breach > 0
            plan = ctx.analysis.sip_plan
            # Redirection fixes drift in either direction: money pointed away
            # from the overweight class is money pointed at the underweight one.
            flow_fix = (
                not plan.requires_sale and plan.months_to_close_gap is not None
                and plan.months_to_close_gap <= 24
            )
            severity = min(1.0, abs(item.breach) / 0.15)
            # Impact is measured from the target, not from the band edge: the
            # money that has to move to fix this is the distance to target, and
            # scoring off the smaller number ranks the largest drift last.
            value = score(impact=min(1.0, abs(item.gap) * 4),
                          urgency=0.45 if flow_fix else 0.7, severity=severity,
                          confidence=0.9, goal_relevance=0.5,
                          irreversible=overweight and not flow_fix).value

            if flow_fix:
                action = Action.REVIEW
                headline = (
                    f"{item.asset_class.value.title()} is {item.breach:+.1%} outside its band -- "
                    + ("redirect contributions rather than sell" if overweight
                       else "point contributions here rather than selling elsewhere")
                )
                tax_impact = "None: redirection uses future contributions, so nothing is realised"
            elif overweight:
                action = Action.REDUCE
                headline = (
                    f"Trim {item.asset_class.value} by about {format_money(gap_value)} "
                    "to return to policy"
                )
                tax_impact = _class_tax_note(ctx, item.asset_class.value)
            else:
                action = Action.BUY_INCREASE
                headline = (
                    f"Add about {format_money(gap_value)} to {item.asset_class.value} "
                    "to return to policy"
                )
                tax_impact = "None: this is a purchase"

            yield ctx.build(
                rule_id="R-ALLOC-DRIFT", action=action,
                subject_id=f"class:{item.asset_class.value}",
                subject_label=item.asset_class.value.title(),
                headline=headline,
                reasons=[
                    f"{item.asset_class.value.title()} is at {item.actual:.1%} against a target of "
                    f"{item.target:.1%} (band {item.lower:.0%}-{item.upper:.0%}).",
                    f"That is {format_money(gap_value)} away from the policy midpoint.",
                    plan.notes[0] if plan.notes and flow_fix else
                    "Drift of this size changes the portfolio's risk, not just its labels.",
                ] + ([
                    "The offsetting side is "
                    + ", ".join(
                        f"{other.asset_class.value} at {other.actual:.1%} against a "
                        f"{other.target:.1%} target"
                        for other in counterparts[:2]
                    )
                    + " -- one move corrects both."
                ] if counterparts else []),
                confidence=0.9,
                priority=priority_for(value),
                evidence=[Evidence(
                    f"Allocation drift: {item.asset_class.value}",
                    ctx.fact_ids(f"allocation.{item.asset_class.value}",
                                 f"drift.{item.asset_class.value}"),
                    f"actual {item.actual:.1%} vs band {item.lower:.0%}-{item.upper:.0%}",
                    "aicio.engine.allocation",
                )],
                portfolio_impact=(
                    f"Returns {item.asset_class.value} to its policy band; expected portfolio "
                    f"volatility moves by roughly {abs(item.breach) * 0.6:.1%}"
                ),
                tax_impact=tax_impact,
                risks=[
                    "Rebalancing sells what has done well and buys what has not, which feels "
                    "wrong precisely when it matters most",
                ],
                counterarguments=[
                    "If the drift came from a deliberate view you still hold, the policy band "
                    "is the thing to change, not the portfolio",
                ],
                alternatives=[
                    "Redirect contributions instead of selling",
                    "Widen the band in the IPS if this drift is acceptable to you",
                ],
                suggested_amount=money(gap_value),
                review_in_days=45,
            )


@rule("R-CONCENTRATION", "A single company above the policy limit, measured look-through")
def concentration_breach(ctx: RuleContext) -> Iterator[Recommendation]:
    """Concentration is measured on companies, not on fund positions.

    A user holding four diversified funds does not have a concentration
    problem, however large each fund is as a share of the portfolio. A user
    with 13% in one bank -- 4% direct and 9% arriving through three funds that
    all hold it -- does, and nothing on a holdings screen shows it.
    """
    limit = ctx.policy.max_single_holding
    # Only the two worst. A user with five names over the limit has one
    # problem, not five, and the third item never gets read.
    for name in ctx.analysis.single_names[:2]:
        excess_value = (name.weight - limit) * ctx.total
        if excess_value < 10000:
            continue
        # Trimming means selling whichever holding carries the exposure. Where
        # it arrives through funds, the honest answer is that no single sale
        # fixes it, so the action becomes a review rather than an instruction.
        direct = [
            ctx.analysis.holding(asset_id) for asset_id, _, _ in name.through
        ]
        direct_views = [view for view in direct if view is not None]
        sellable = [
            view for view in direct_views
            if not view.locked and ctx.portfolio.asset(view.holding.asset_id).ticker.upper()
            == name.key.upper()
        ]
        tax_note = "Cost basis unknown, so the tax cost of trimming cannot be estimated"
        if sellable and sellable[0].unrealised:
            view = sellable[0]
            share = min(1.0, excess_value / max(1.0, view.market_value))
            cost = exit_tax_cost(
                _proportional(view.unrealised, share),
                marginal_rate=ctx.profile.marginal_tax_rate,
                exemption_left=ctx.analysis.tax.ltcg_exemption_left,
            )
            tax_note = f"Trimming to the limit would realise about {format_money(cost)} in tax"
        locked = next((v.locked for v in direct_views if v.locked), "")

        through = ", ".join(label for _, label, _ in name.through[:3])
        value = score(impact=min(1.0, (name.weight - limit) * 6), urgency=0.6,
                      severity=min(1.0, (name.weight - limit) / limit),
                      confidence=0.85, goal_relevance=0.4).value
        yield ctx.build(
            rule_id="R-CONCENTRATION",
            action=Action.REDUCE if sellable and not locked else Action.REVIEW,
            subject_id=(
                sellable[0].holding.asset_id if sellable else f"company:{name.key}"
            ),
            subject_label=name.label,
            headline=(
                f"{name.label} is {name.weight:.1%} of the portfolio, above the {limit:.0%} limit"
                + ("" if name.direct_only else f" -- reaching you through {len(name.through)} holdings")
            ),
            confidence=0.85,
            # Twice the policy limit in one name is a different category of
            # problem from a few points over, and is escalated regardless of
            # how the rest of the score lands.
            priority=priority_for(value, safety_critical=name.weight > 2 * limit),
            reasons=[
                f"Look-through exposure to {name.label} is {name.weight:.1%}; policy allows "
                f"{limit:.0%}.",
                f"About {format_money(excess_value)} sits above the limit.",
                (f"It arrives through {through}, so no single sale fixes it."
                 if not name.direct_only else
                 "A single-name shock here moves the whole plan, not one line of it."),
            ] + ([f"Part of the exposure is locked: {locked}."] if locked else []),
            evidence=[Evidence(
                "Look-through single-name exposure",
                ctx.fact_ids(f"single_name.{name.key}", "lookthrough.top_company"),
                f"{name.weight:.2%} of portfolio across {len(name.through)} holding(s)",
                "aicio.engine.xray",
            )],
            portfolio_impact=(
                f"Reduces single-name risk; effective positions currently "
                f"{ctx.analysis.concentration.effective_positions:.1f}"
            ),
            tax_impact=tax_note,
            risks=[
                "Trimming a winner caps the upside if the thesis is right",
                "Selling in one block can move the price in a thin stock",
            ],
            counterarguments=[
                "Concentration is how wealth is built; the limit exists to protect wealth "
                "already built, and you may deliberately accept this one",
                "If this is founder or employer stock, the right fix may be diversifying "
                "the rest rather than selling this",
                f"Look-through covers {ctx.analysis.xray.coverage:.0%} of the portfolio, so "
                "the true exposure could be higher or lower",
            ],
            alternatives=[
                "Trim in tranches across financial years to spread the tax",
                "Stop new contributions to whatever carries this exposure",
                "Raise the single-holding limit in the IPS if this is a considered choice",
            ],
            suggested_amount=money(excess_value),
            review_in_days=60,
        )


@rule("R-POSITION-SIZE", "One fund holding an outsized share of the portfolio")
def position_size(ctx: RuleContext) -> Iterator[Recommendation]:
    """Manager risk, which is a different thing from single-name risk.

    Fires at a much looser threshold than the single-name limit, because a
    concentrated *fund* lineup is only a problem when one manager's process
    governs most of the money.
    """
    from ..engine.allocation import POSITION_LIMIT

    for asset_id, label, weight in ctx.analysis.concentration.top[:1]:
        if weight <= POSITION_LIMIT:
            continue
        view = ctx.analysis.holding(asset_id)
        if view is None:
            continue
        value = score(impact=min(1.0, (weight - POSITION_LIMIT) * 3), urgency=0.35,
                      severity=min(1.0, (weight - POSITION_LIMIT) / POSITION_LIMIT),
                      confidence=0.7, goal_relevance=0.25).value
        yield ctx.build(
            rule_id="R-POSITION-SIZE", action=Action.REVIEW, subject_id=asset_id,
            subject_label=label,
            headline=f"{weight:.0%} of the portfolio sits with one fund manager",
            reasons=[
                f"{label} is {weight:.1%} of invested value.",
                "Its underlying companies may be diversified, but its process, its risk "
                "controls and its manager are not.",
                "A second fund with a genuinely different strategy spreads that.",
            ],
            confidence=0.7,
            priority=priority_for(value),
            evidence=[Evidence(
                "Position weight", ctx.fact_ids(f"position_weight.{asset_id}"),
                f"{weight:.1%} of invested value", "aicio.engine.allocation",
            )],
            portfolio_impact="Spreads manager risk without changing asset allocation",
            tax_impact="Only if you move money; redirecting contributions costs nothing",
            risks=["Adding funds for their own sake produces overlap, not diversification"],
            counterarguments=[
                "A single low-cost index fund at any weight is a defensible whole portfolio",
            ],
            alternatives=["Point new contributions at a different strategy instead of selling"],
            review_in_days=180,
        )


@rule("R-SECTOR", "Look-through sector exposure above the policy limit")
def sector_breach(ctx: RuleContext) -> Iterator[Recommendation]:
    limit = ctx.policy.max_sector
    for exposure in ctx.analysis.xray.by_sector[:4]:
        if exposure.weight <= limit or exposure.key in {"cash", "diversified"}:
            continue
        contributors = ", ".join(label for _, label, _ in exposure.contributors[:3])
        value = score(impact=min(1.0, (exposure.weight - limit) * 5), urgency=0.5,
                      severity=min(1.0, (exposure.weight - limit) / limit),
                      confidence=0.75, goal_relevance=0.35).value
        yield ctx.build(
            rule_id="R-SECTOR", action=Action.REVIEW,
            subject_id=f"sector:{exposure.key}", subject_label=exposure.label,
            headline=f"{exposure.label} is {exposure.weight:.0%} of the portfolio once funds are looked through",
            reasons=[
                f"Look-through exposure to {exposure.label} is {exposure.weight:.1%} "
                f"against a {limit:.0%} limit.",
                f"It arrives through {len(exposure.contributors)} holdings, mainly {contributors}.",
                "None of the individual holdings looks concentrated; the exposure is only "
                "visible when the funds are opened up.",
            ],
            confidence=0.75,
            priority=priority_for(value),
            evidence=[Evidence(
                "Look-through sector exposure", ctx.fact_ids("lookthrough.top_company"),
                f"{exposure.label} at {exposure.weight:.1%} of {format_money(ctx.analysis.xray.total)}",
                "aicio.engine.xray",
            )],
            portfolio_impact="Reducing sector overlap lowers correlated drawdown",
            tax_impact="Depends which holding is trimmed; see the individual position",
            risks=["Sector classification varies between data providers"],
            counterarguments=[
                f"Indian equity indices are themselves heavy in {exposure.label}; "
                "matching the index is not the same as taking a bet",
                f"Look-through covers {ctx.analysis.xray.coverage:.0%} of the portfolio, "
                "so the true figure could differ",
            ],
            alternatives=[
                "Point new contributions at funds with different sector exposure",
                "Consolidate overlapping funds rather than reducing exposure outright",
            ],
            review_in_days=90,
        )


@rule("R-OVERLAP", "Funds that hold substantially the same portfolio")
def fund_overlap(ctx: RuleContext) -> Iterator[Recommendation]:
    material = [o for o in ctx.analysis.overlaps if o.overlap >= 0.55]
    # One item for the worst pair. Three funds tracking the same index produce
    # three pairs and one decision, so the others are named inside the reasons
    # rather than queued as separate work.
    for overlap in material[:1]:
        others = material[1:]
        left = ctx.analysis.holding(overlap.left_id)
        right = ctx.analysis.holding(overlap.right_id)
        if left is None or right is None:
            continue
        smaller = min(left, right, key=lambda v: v.market_value)
        shared = ", ".join(ticker for ticker, _ in overlap.shared[:4])
        value = score(impact=min(1.0, overlap.overlap), urgency=0.3,
                      severity=overlap.overlap, confidence=0.8, goal_relevance=0.2).value
        yield ctx.build(
            rule_id="R-OVERLAP", action=Action.REVIEW,
            subject_id=smaller.holding.asset_id, subject_label=smaller.label,
            headline=(
                f"{overlap.left_name} and {overlap.right_name} overlap {overlap.overlap:.0%} -- "
                "you are paying twice for one exposure"
            ),
            reasons=[
                f"The two funds share {overlap.overlap:.0%} of their disclosed holdings "
                f"({overlap.absolute_overlap:.0%} of total fund value, since factsheets "
                "publish only the largest positions).",
                f"Largest shared names: {shared}.",
                "Holding both adds cost and admin without adding diversification.",
            ] + ([
                f"{len(others)} further fund pair(s) overlap above 55%: "
                + "; ".join(f"{o.left_name} / {o.right_name} at {o.overlap:.0%}"
                            for o in others[:2])
            ] if others else []),
            confidence=0.8,
            priority=priority_for(value),
            evidence=[Evidence(
                "Fund overlap",
                ctx.fact_ids(f"overlap.{overlap.left_id}.{overlap.right_id}"),
                f"{overlap.overlap:.1%} weighted overlap", "aicio.engine.xray",
            )],
            portfolio_impact="Consolidating simplifies the portfolio without changing exposure",
            tax_impact=(
                "Switching between funds is a redemption for tax; check the gain on the "
                "smaller holding before acting"
            ),
            risks=["Consolidating into one fund concentrates manager risk"],
            counterarguments=[
                "Two funds with the same holdings can still behave differently in a "
                "drawdown if their cash and turnover policies differ",
                "Overlap is measured from published holdings, which lag by a month",
            ],
            alternatives=[
                f"Stop contributions to {smaller.label} and let it run down rather than selling",
                "Keep both but redirect new money to a genuinely different strategy",
            ],
            review_in_days=120,
        )


# ---------------------------------------------------------------------------
# Goals and contributions
# ---------------------------------------------------------------------------

@rule("R-GOAL-SHORTFALL", "A goal whose probability has fallen below the bar")
def goal_shortfall(ctx: RuleContext) -> Iterator[Recommendation]:
    for projection in ctx.analysis.projections:
        if projection.on_track:
            continue
        extra = max(0.0, projection.required_monthly - projection.monthly_contribution)
        value = score(
            impact=min(1.0, 1.0 - projection.probability),
            urgency=0.8 if projection.years < 5 else 0.5,
            severity=min(1.0, (0.7 - projection.probability) / 0.7),
            confidence=0.8, goal_relevance=1.0,
        ).value
        yield ctx.build(
            rule_id="R-GOAL-SHORTFALL", action=Action.REVIEW,
            subject_id=projection.goal_id, subject_label=projection.goal_name,
            headline=(
                f"'{projection.goal_name}' has a {projection.probability:.0%} chance of being met "
                "on the current plan"
            ),
            reasons=[
                f"Target of {format_money(projection.target_nominal)} in "
                f"{projection.years:.1f} years, inflation-adjusted.",
                f"Median simulated outcome is {format_money(projection.percentiles['p50'])}; "
                f"the tenth percentile is {format_money(projection.percentiles['p10'])}.",
                (f"Closing the gap through contributions alone needs about "
                 f"{format_money(extra)} more per month.") if extra > 0 else
                "The gap is in the return assumption rather than the contribution.",
            ],
            confidence=0.8,
            priority=priority_for(value),
            evidence=[Evidence(
                "Goal projection",
                ctx.fact_ids(f"goal.{projection.goal_id}.probability",
                             f"goal.{projection.goal_id}.required_monthly"),
                f"{projection.trials} simulated paths at {projection.expected_return:.1%} "
                f"expected return, {projection.expected_volatility:.1%} volatility",
                "aicio.engine.goals",
            )],
            portfolio_impact=(
                f"Raising contributions by {format_money(extra)}/month closes the gap on "
                "current assumptions; the scenario table shows what each lever is worth"
                if extra > 0 else
                "Contributions are already at the level the plan needs. What is short is the "
                "return assumption or the time available, so the levers are the date and the "
                "target rather than the monthly amount."
            ),
            tax_impact="None from contributing more",
            risks=[
                "The projection rests on long-run return assumptions that no one can "
                "guarantee; the range matters more than the median",
            ],
            counterarguments=[
                "Delaying the goal by two years is often worth more than any feasible "
                "increase in contributions, and costs nothing today",
                f"A {projection.probability:.0%} probability over {projection.years:.0f} years "
                "has plenty of time to self-correct",
            ],
            alternatives=[
                "Push the target date out",
                "Lower the target amount",
                "Raise the contribution",
                "Take more equity risk -- only if risk capacity allows it",
            ],
            goal_ids=(projection.goal_id,),
            review_in_days=90,
        )


@rule("R-SIP-REDIRECT", "Contributions pointed at the wrong asset class")
def sip_redirect(ctx: RuleContext) -> Iterator[Recommendation]:
    plan = ctx.analysis.sip_plan
    changed = plan.changed
    if not changed or not plan.new_allocations:
        return
    moving = sum(as_float(c.current_amount) for c in changed if c.proposed_amount == 0)
    if moving < 1000:
        return
    destinations = ", ".join(
        f"{row['asset_class']} {format_money(row['monthly_amount'])}"
        for row in plan.new_allocations[:3]
    )
    value = score(impact=min(1.0, moving / max(1.0, as_float(plan.monthly_total))),
                  urgency=0.4, severity=0.5, confidence=0.85, goal_relevance=0.6).value
    yield ctx.build(
        rule_id="R-SIP-REDIRECT", action=Action.REVIEW, subject_id="sips",
        subject_label="Monthly contributions",
        headline=f"Redirect {format_money(moving)}/month to what the policy is short of",
        reasons=[
            f"{len(changed)} of {len(plan.changes)} contributions feed classes already at or "
            "above their policy band.",
            f"Proposed destinations: {destinations}.",
            plan.notes[0] if plan.notes else
            "Redirecting future money corrects drift without selling anything.",
        ],
        confidence=0.85,
        priority=priority_for(value),
        evidence=[Evidence(
            "SIP optimisation", ctx.fact_ids("allocation.equity", "allocation.debt"),
            f"{format_money(plan.monthly_total)}/month across {len(plan.changes)} mandates",
            "aicio.engine.sip",
        )],
        portfolio_impact=(
            "Moves the allocation towards policy over "
            + (f"{plan.months_to_close_gap:.0f} months" if plan.months_to_close_gap
               else "the medium term")
            + " with no sale"
        ),
        tax_impact="None: no units are redeemed",
        risks=["Stopping a SIP into a good fund to fix allocation can feel like a downgrade"],
        counterarguments=[
            "If the overweight class is where your conviction is, changing the policy "
            "band is the honest fix rather than redirecting money away from it",
        ],
        alternatives=[
            "Keep existing mandates and add new ones only to underweight classes",
            "Do nothing and let the next market move close some of the gap",
        ],
        suggested_amount=money(moving),
        review_in_days=60,
    )


@rule("R-CASH-DRAG", "Idle cash well beyond what the plan needs")
def cash_drag(ctx: RuleContext) -> Iterator[Recommendation]:
    cash = as_float(ctx.portfolio.cash)
    months = ctx.analysis.liquid_months
    if cash <= 0 or months is None:
        return
    monthly = as_float(ctx.profile.annual_expenses) / 12
    buffer_months = ctx.policy.min_emergency_months + 3
    if months <= buffer_months:
        return
    deployable = money((months - buffer_months) * monthly)
    value = score(impact=min(1.0, as_float(deployable) / max(1.0, ctx.total) * 3),
                  urgency=0.35, severity=min(1.0, (months - buffer_months) / 12),
                  confidence=0.85, goal_relevance=0.5).value
    yield ctx.build(
        rule_id="R-CASH-DRAG", action=Action.BUY_INCREASE, subject_id="cash",
        subject_label="Idle cash",
        headline=f"{format_money(deployable)} of cash is doing nothing",
        reasons=[
            f"Cash covers {months:.0f} months of expenses; the plan needs {buffer_months}.",
            f"The excess of {format_money(deployable)} is losing real value to inflation "
            f"at roughly {ctx.analysis.projections[0].assumptions['inflation']:.0%} a year."
            if ctx.analysis.projections else
            f"The excess of {format_money(deployable)} is losing real value to inflation.",
            "Deploying it gradually avoids putting the whole amount in at one price.",
        ],
        confidence=0.85,
        priority=priority_for(value),
        evidence=[Evidence("Cash position", ctx.fact_ids("cash", "liquid_months"),
                           f"{format_money(cash)} against {months:.1f} months of expenses")],
        portfolio_impact=f"Puts {format_money(deployable)} to work in underweight classes",
        tax_impact="None on deployment; future gains will be taxable",
        risks=[
            "Deploying into a falling market feels worse than holding cash, and the "
            "first months may show a loss",
        ],
        counterarguments=[
            "If a large near-term expense is coming that we do not know about, this cash "
            "is correctly parked",
            "Cash is the only asset that is certain to be there when it is needed",
        ],
        alternatives=[
            f"Stage it over 4-6 months rather than deploying at once",
            "Park it in a liquid fund for a better yield while deciding",
        ],
        suggested_amount=deployable,
        review_in_days=45,
    )


# ---------------------------------------------------------------------------
# Holdings
# ---------------------------------------------------------------------------

@rule("R-FUND-QUALITY", "A fund whose evidence has deteriorated")
def fund_quality(ctx: RuleContext) -> Iterator[Recommendation]:
    for view in ctx.analysis.holdings:
        if view.quality is None or view.quality >= 45 or view.weight < 0.02:
            continue
        asset = ctx.portfolio.asset(view.holding.asset_id)
        tax_note = "Cost basis unknown; the tax cost of switching cannot be estimated"
        if view.unrealised:
            cost = exit_tax_cost(
                view.unrealised, marginal_rate=ctx.profile.marginal_tax_rate,
                exemption_left=ctx.analysis.tax.ltcg_exemption_left,
            )
            tax_note = f"A full switch would realise about {format_money(cost)} in tax"
        short_term = [p for p in view.unrealised if p.gain_type == GainType.SHORT_TERM and p.gain > 0]
        value = score(impact=min(1.0, view.weight * 5), urgency=0.4,
                      severity=(45 - view.quality) / 45, confidence=0.7,
                      goal_relevance=0.3, irreversible=True).value
        yield ctx.build(
            rule_id="R-FUND-QUALITY",
            action=Action.REVIEW if view.locked or short_term else Action.EXIT_SWITCH,
            subject_id=view.holding.asset_id, subject_label=view.label,
            headline=f"{view.label} no longer earns its place on the evidence",
            reasons=[
                f"Quality assessment is {view.quality:.0f}/100, below the review threshold of 45.",
                f"It is {view.weight:.1%} of the portfolio, worth {format_money(view.market_value)}.",
                f"Lock-in applies: {view.locked}." if view.locked else
                ("Part of the holding is still short-term for tax, so a switch today costs more."
                 if short_term else
                 "A switch to a stronger fund in the same category is available without "
                 "changing the portfolio's risk."),
            ],
            confidence=0.7,
            priority=priority_for(value),
            evidence=[Evidence(
                "Fund quality assessment", ctx.fact_ids("health.quality"),
                f"score {view.quality:.0f}/100 from returns, costs and consistency",
                asset.benchmark or "category evidence",
            )],
            portfolio_impact="Replaces the exposure rather than removing it, so allocation is unchanged",
            tax_impact=tax_note,
            risks=[
                "Switching funds resets the holding period for tax",
                "Underperformance often mean-reverts; selling after a bad run is a "
                "well-documented way to lock it in",
            ],
            counterarguments=[
                "Three years is a short window for a fund manager, and style is cyclical",
                "The replacement's record is measured over a different period, which "
                "flatters it",
            ],
            alternatives=[
                "Stop contributions and hold the existing units",
                "Switch in tranches across financial years",
                "Wait until the short-term units turn long-term",
            ],
            review_in_days=90,
        )


# ---------------------------------------------------------------------------
# Tax
# ---------------------------------------------------------------------------

@rule("R-TAX-HARVEST", "Unused annual capital-gains exemption")
def tax_harvest(ctx: RuleContext) -> Iterator[Recommendation]:
    left = as_float(ctx.analysis.tax.ltcg_exemption_left)
    if left < 25000:
        return
    harvestable = [
        p for view in ctx.analysis.holdings for p in view.unrealised
        if p.gain_type == GainType.LONG_TERM and p.gain > 0
    ]
    available = sum(as_float(p.gain) for p in harvestable)
    if available < 25000:
        return
    usable = min(left, available)
    if ctx.today.month < 10:
        # Before October there is most of a financial year left to use the
        # exemption, and harvesting early forgoes optionality for no gain.
        return
    value = score(impact=min(1.0, usable / 125000), urgency=0.75 if ctx.today.month >= 1 else 0.5,
                  severity=0.4, confidence=0.8, goal_relevance=0.2).value
    yield ctx.build(
        rule_id="R-TAX-HARVEST", action=Action.REVIEW, subject_id="tax",
        subject_label="Capital gains exemption",
        headline=f"{format_money(left)} of this year's LTCG exemption is still unused",
        reasons=[
            f"Long-term gains of about {format_money(available)} are available to realise.",
            f"Realising up to {format_money(usable)} and buying back resets the cost basis "
            "higher at no tax cost.",
            "The exemption does not carry forward: unused, it is gone on 31 March.",
        ],
        confidence=0.8,
        priority=priority_for(value),
        evidence=[Evidence("Tax position", ctx.fact_ids("tax.ltcg_exemption_left", "tax.estimated"),
                           f"{format_money(left)} of exemption remaining",
                           "aicio.engine.taxlots")],
        portfolio_impact="No change in exposure if the same units are bought back",
        tax_impact=f"Realises up to {format_money(usable)} of gain at zero tax",
        risks=[
            "The buy-back happens at a market price that may have moved",
            "Exit loads and transaction costs can exceed the tax saved on small amounts",
        ],
        counterarguments=[
            "Harvesting is only worth it if the position is one you want to keep anyway",
            "Tax rules and this estimate should be confirmed with your tax adviser",
        ],
        alternatives=["Harvest part of the gain", "Do nothing and carry the higher basis later"],
        review_in_days=30,
    )


@rule("R-TAX-WAIT", "A sale that would be materially cheaper in a few weeks")
def tax_wait(ctx: RuleContext) -> Iterator[Recommendation]:
    near = ctx.analysis.tax.near_long_term
    if not near:
        return
    soonest = near[0]
    view = ctx.analysis.holding(soonest.asset_id)
    if view is None:
        return
    saving = as_float(soonest.gain) * 0.075          # 20% STCG against 12.5% LTCG
    if saving < 5000:
        return
    yield ctx.build(
        rule_id="R-TAX-WAIT", action=Action.HOLD, subject_id=soonest.asset_id,
        subject_label=view.label,
        headline=(
            f"{view.label} becomes long-term in {soonest.days_to_long_term} days -- "
            "any sale should wait"
        ),
        reasons=[
            f"The oldest short-term lot was bought on {soonest.acquired_on.isoformat()}.",
            f"Waiting {soonest.days_to_long_term} days cuts the tax on "
            f"{format_money(soonest.gain)} of gain by roughly {format_money(saving)}.",
            "Nothing else about the holding argues for selling today.",
        ],
        confidence=0.9,
        priority=Priority.MEDIUM,
        evidence=[Evidence("Tax lot ageing", ctx.fact_ids("tax.estimated"),
                           f"lot acquired {soonest.acquired_on.isoformat()}, "
                           f"{soonest.holding_days} days held", "aicio.engine.taxlots")],
        portfolio_impact="None",
        tax_impact=f"Saves about {format_money(saving)} against selling today",
        risks=["The price can fall by more than the tax saved while waiting"],
        counterarguments=["If the reason to sell is risk rather than return, tax should not decide it"],
        alternatives=["Sell the long-term lots now and the short-term ones after the date"],
        review_in_days=max(7, soonest.days_to_long_term),
    )


def _proportional(positions, fraction: float):
    """Scale a set of tax lots down to the fraction actually being sold."""
    from dataclasses import replace
    from ..money import quantity
    out = []
    for position in positions:
        out.append(replace(
            position,
            units=quantity(as_float(position.units) * fraction),
            cost=money(as_float(position.cost) * fraction),
            value=money(as_float(position.value) * fraction),
        ))
    return out


def _class_tax_note(ctx: RuleContext, asset_class: str) -> str:
    positions = [
        p for view in ctx.analysis.holdings
        if view.asset_class.value == asset_class
        for p in view.unrealised
    ]
    if not positions:
        return "Cost basis is incomplete, so the tax cost of trimming cannot be estimated"
    cost = exit_tax_cost(
        positions, marginal_rate=ctx.profile.marginal_tax_rate,
        exemption_left=ctx.analysis.tax.ltcg_exemption_left,
    )
    return f"Selling the whole overweight would realise about {format_money(cost)} in tax"
