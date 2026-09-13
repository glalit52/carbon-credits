"""Daily brief, weekly report, monthly investment committee.

Three cadences, three genuinely different jobs -- which is why they are three
functions and not one function with a period argument:

*   The **daily brief** answers "is anything on fire". Most days the answer is
    no, and it says so in one line rather than manufacturing content.
*   The **weekly report** is a portfolio review: what moved, what drifted, what
    the open decisions are.
*   The **monthly investment committee** is the one a private bank would hold:
    policy versus reality, goals, risk, tax position, and a decision log of
    what was recommended and what the client did about it.

All three are assembled from the deterministic analysis. The AI layer may
rewrite them into better prose; it may not add a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Sequence

from .analysis import PortfolioAnalysis
from .decisions.engine import RecommendationSet
from .domain import (
    Alert, DecisionOutcome, DecisionRecord, Priority,
)
from .money import as_float, format_money, pct


@dataclass
class Section:
    title: str
    lines: list[str] = field(default_factory=list)
    #: Facts backing this section, so a reader can trace any figure in it.
    fact_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "lines": list(self.lines), "fact_ids": list(self.fact_ids)}


@dataclass
class Report:
    kind: str
    user_id: str
    as_of: date
    headline: str
    sections: list[Section] = field(default_factory=list)
    nothing_to_do: bool = False

    def render(self) -> str:
        out = [self.headline, "=" * len(self.headline), ""]
        for section in self.sections:
            out.append(section.title)
            out.append("-" * len(section.title))
            out.extend(f"  {line}" for line in section.lines)
            out.append("")
        return "\n".join(out).rstrip() + "\n"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "user_id": self.user_id, "as_of": self.as_of.isoformat(),
            "headline": self.headline, "nothing_to_do": self.nothing_to_do,
            "sections": [s.to_dict() for s in self.sections],
        }


def _money(value: float) -> str:
    return format_money(value, compact=abs(value) >= 100000)


def daily_brief(
    analysis: PortfolioAnalysis,
    recommendations: RecommendationSet,
    alerts: Sequence[Alert] = (),
    *,
    previous: PortfolioAnalysis | None = None,
) -> Report:
    """One screen. Most days it should say nothing needs doing."""
    critical = [a for a in alerts if a.severity == Priority.CRITICAL]
    urgent = [r for r in recommendations.recommendations
              if r.priority in {Priority.CRITICAL, Priority.HIGH}]
    quiet = not critical and not urgent

    headline = (
        f"Daily brief · {analysis.as_of.isoformat()} · "
        + ("nothing needs your attention" if quiet else f"{len(urgent) + len(critical)} to look at")
    )
    report = Report("daily", analysis.user_id, analysis.as_of, headline, nothing_to_do=quiet)

    position = Section("Where you stand", fact_ids=tuple(analysis.facts.ids[:3]))
    position.lines.append(
        f"Net worth {_money(analysis.net_worth)} · invested "
        f"{_money(as_float(analysis.portfolio.market_value))} · cash "
        f"{_money(as_float(analysis.portfolio.cash))}"
    )
    if previous is not None:
        change = analysis.net_worth - previous.net_worth
        base = previous.net_worth or 1.0
        position.lines.append(
            f"Change since {previous.as_of.isoformat()}: {_money(change)} ({pct(change / base)})"
        )
    position.lines.append(
        f"Health {analysis.health.score:.0f}/100 ({analysis.health.band})"
        + (f" · weakest: {analysis.health.weakest.label}" if analysis.health.weakest else "")
    )
    report.sections.append(position)

    if critical:
        section = Section("Needs attention now")
        for alert in critical:
            section.lines.append(f"[critical] {alert.title} — {alert.body}")
        report.sections.append(section)

    if urgent:
        section = Section("Decisions waiting")
        for recommendation in urgent:
            section.lines.append(
                f"[{recommendation.priority.value}] {recommendation.action.value}: "
                f"{recommendation.headline}"
            )
        report.sections.append(section)
    elif quiet:
        section = Section("Why there is nothing to do")
        do_nothing = next(
            (r for r in recommendations.recommendations if r.rule_id == "R-NONE"), None
        )
        if do_nothing is not None:
            section.lines.extend(do_nothing.reasons)
        else:
            section.lines.append(
                "Everything open is low priority and can wait for the weekly review."
            )
        report.sections.append(section)

    return report


def weekly_report(
    analysis: PortfolioAnalysis,
    recommendations: RecommendationSet,
    *,
    previous: PortfolioAnalysis | None = None,
) -> Report:
    report = Report(
        "weekly", analysis.user_id, analysis.as_of,
        f"Weekly portfolio report · week ending {analysis.as_of.isoformat()}",
    )

    performance = Section("Performance", fact_ids=tuple(analysis.facts.ids[:5]))
    performance.lines.append(
        f"Invested {_money(as_float(analysis.portfolio.invested))} · value "
        f"{_money(as_float(analysis.portfolio.market_value))} · unrealised "
        f"{_money(as_float(analysis.portfolio.unrealised_gain))}"
    )
    if analysis.portfolio_xirr is not None:
        performance.lines.append(
            f"XIRR since inception {pct(analysis.portfolio_xirr)} "
            "(money-weighted, so it reflects your timing as well as the funds')"
        )
    best = max(analysis.holdings, key=lambda v: v.gain_pct, default=None)
    worst = min(analysis.holdings, key=lambda v: v.gain_pct, default=None)
    if best is not None and worst is not None and best is not worst:
        performance.lines.append(
            f"Best: {best.label} {pct(best.gain_pct)} · worst: {worst.label} {pct(worst.gain_pct)}"
        )
    report.sections.append(performance)

    allocation = Section("Allocation against policy")
    for item in analysis.drift.drifts:
        flag = "" if item.in_band else "  ← outside band"
        allocation.lines.append(
            f"{item.asset_class.value:<12} {item.actual:6.1%}  target {item.target:5.1%}"
            f"  band {item.lower:.0%}-{item.upper:.0%}{flag}"
        )
    report.sections.append(allocation)

    if analysis.xray.by_sector:
        xray = Section("What you actually own")
        for exposure in analysis.xray.by_sector[:5]:
            xray.lines.append(f"{exposure.label:<18} {exposure.weight:6.1%}")
        if analysis.xray.coverage < 1:
            xray.lines.append(
                f"(look-through covers {analysis.xray.coverage:.0%} of value; the rest is "
                "inside funds that do not publish full holdings)"
            )
        report.sections.append(xray)

    decisions = Section("Open decisions")
    for recommendation in recommendations.recommendations:
        decisions.lines.append(
            f"[{recommendation.priority.value}] {recommendation.action.value}: "
            f"{recommendation.headline}"
        )
    if not recommendations.recommendations:
        decisions.lines.append("None.")
    report.sections.append(decisions)

    return report


def monthly_committee(
    analysis: PortfolioAnalysis,
    recommendations: RecommendationSet,
    *,
    history: Sequence[DecisionRecord] = (),
    previous: PortfolioAnalysis | None = None,
) -> Report:
    """The monthly personal investment committee.

    Structured the way a real investment committee paper is: policy first,
    then whether reality matches it, then risk, then goals, then the decision
    log. Performance comes late on purpose -- it is the output of the process,
    not the agenda.
    """
    report = Report(
        "monthly", analysis.user_id, analysis.as_of,
        f"Personal investment committee · {analysis.as_of.strftime('%B %Y')}",
    )

    policy = Section("1. Policy")
    policy.lines.append(analysis.policy.objective)
    policy.lines.append(
        f"Horizon {analysis.policy.horizon_years} years · review every "
        f"{analysis.policy.review_frequency_months} months · "
        f"risk capacity {analysis.profile.risk_capacity}/10, "
        f"tolerance {analysis.profile.risk_tolerance}/10"
    )
    if analysis.profile.risk_gap >= 3:
        policy.lines.append(
            "Note: stated tolerance exceeds measured capacity; policy follows capacity."
        )
    report.sections.append(policy)

    adherence = Section("2. Adherence")
    adherence.lines.append(
        f"Total drift from policy: {analysis.drift.total_absolute_drift:.1%}"
    )
    for item in analysis.drift.breaches:
        adherence.lines.append(
            f"Breach — {item.asset_class.value}: {item.actual:.1%} against "
            f"{item.lower:.0%}-{item.upper:.0%}; "
            f"{_money(abs(item.breach) * analysis.drift.total)} beyond the band, "
            f"{_money(abs(item.gap) * analysis.drift.total)} from target"
        )
    if not analysis.drift.breaches:
        adherence.lines.append("No breaches. Allocation is inside every band.")
    report.sections.append(adherence)

    risk = Section("3. Risk")
    risk.lines.append(
        f"Effective positions {analysis.concentration.effective_positions:.1f} "
        f"(HHI {analysis.concentration.hhi:.3f})"
    )
    for scenario in analysis.scenarios[:3]:
        cover = (
            f", liquidity {scenario.liquidity_months_after:.0f} months after"
            if scenario.liquidity_months_after is not None else ""
        )
        risk.lines.append(
            f"{scenario.name}: {_money(scenario.loss)} ({pct(scenario.loss_pct)}){cover}"
        )
    report.sections.append(risk)

    if analysis.projections:
        goals = Section("4. Goals")
        for projection in analysis.projections:
            goals.lines.append(
                f"{projection.goal_name}: {projection.probability:.0%} "
                f"({projection.status.replace('_', ' ')}) — target "
                f"{_money(projection.target_nominal)} in {projection.years:.1f} years, "
                f"median outcome {_money(projection.percentiles['p50'])}"
            )
        report.sections.append(goals)

    tax = Section("5. Tax")
    tax.lines.append(
        f"Realised this year — short term {format_money(analysis.tax.realised_short_term)}, "
        f"long term {format_money(analysis.tax.realised_long_term)}"
    )
    tax.lines.append(
        f"Estimated tax {format_money(analysis.tax.estimated_tax)} · exemption remaining "
        f"{format_money(analysis.tax.ltcg_exemption_left)}"
    )
    if analysis.tax.near_long_term:
        nearest = analysis.tax.near_long_term[0]
        tax.lines.append(
            f"{len(analysis.tax.near_long_term)} lot(s) approach long-term treatment; "
            f"the nearest in {nearest.days_to_long_term} days"
        )
    for note in analysis.tax.notes[:2]:
        tax.lines.append(f"Note: {note}")
    report.sections.append(tax)

    decisions = Section("6. Decisions")
    for recommendation in recommendations.recommendations:
        decisions.lines.append(
            f"[{recommendation.priority.value}] {recommendation.action.value} — "
            f"{recommendation.headline}"
        )
    if recommendations.suppressed:
        decisions.lines.append(
            f"({len(recommendations.suppressed)} further findings were held back: "
            + "; ".join(r.suppressed_reason for r in recommendations.suppressed[:2]) + ")"
        )
    report.sections.append(decisions)

    if history:
        log = Section("7. Decision log")
        for record in sorted(history, key=lambda r: r.decided_at, reverse=True)[:8]:
            log.lines.append(
                f"{record.decided_at.date().isoformat()} — {record.outcome.value}"
                + (f": {record.note}" if record.note else "")
            )
        accepted = sum(1 for r in history if r.outcome == DecisionOutcome.ACCEPTED)
        log.lines.append(
            f"{accepted} of {len(history)} recommendations acted on to date."
        )
        report.sections.append(log)

    return report
