"""Running the rules, and deciding what survives to the user.

The pipeline, in order, and each step exists because of a specific failure it
prevents:

1.  **Run every rule.** Rules do not know about each other, so nothing can be
    suppressed by ordering accidents.
2.  **Validate.** A recommendation missing evidence, risks or a counterargument
    is a bug, and it is dropped loudly rather than shown.
3.  **Suitability gate.** Policy constraints block material actions here, once,
    rather than being re-checked in each rule and eventually forgotten in one.
4.  **De-duplicate.** Two rules can reach the same subject from different
    directions; the user should see the stronger one, not both.
5.  **Suppress against history.** A user who declined this exact suggestion
    twice should not be shown it a third time unchanged.
6.  **Rank and cap.** An action centre with fourteen items is a to-do list
    nobody starts.
7.  **DO_NOTHING.** If nothing survives, say so deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Sequence

from .. import ENGINE_VERSION
from ..analysis import PortfolioAnalysis
from ..domain import (
    Action, DecisionOutcome, DecisionRecord, Evidence, Priority,
    Recommendation, new_id,
)
from ..ips import check_suitability
from .rules import RULES, RuleContext
from .scoring import rank

#: How many items reach the action centre. Five is what a person will actually
#: read; the rest stay available in the full list.
DEFAULT_LIMIT = 5

#: A suggestion declined this many times stops being shown until the underlying
#: state changes materially.
DECLINE_TOLERANCE = 2


@dataclass
class RecommendationSet:
    """What the engine decided, including what it decided not to show."""

    user_id: str
    as_of: date
    recommendations: list[Recommendation]
    suppressed: list[Recommendation] = field(default_factory=list)
    invalid: list[tuple[str, list[str]]] = field(default_factory=list)
    rules_fired: list[str] = field(default_factory=list)
    engine_version: str = ENGINE_VERSION
    portfolio_fingerprint: str = ""

    @property
    def top(self) -> list[Recommendation]:
        return self.recommendations[:DEFAULT_LIMIT]

    @property
    def do_nothing(self) -> bool:
        return (
            len(self.recommendations) == 1
            and self.recommendations[0].action == Action.DO_NOTHING
        )

    def by_priority(self, priority: Priority) -> list[Recommendation]:
        return [r for r in self.recommendations if r.priority == priority]

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "as_of": self.as_of.isoformat(),
            "engine_version": self.engine_version,
            "portfolio_fingerprint": self.portfolio_fingerprint,
            "do_nothing": self.do_nothing,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "suppressed": [
                {"id": r.id, "rule_id": r.rule_id, "subject": r.subject_label,
                 "reason": r.suppressed_reason}
                for r in self.suppressed
            ],
            "invalid": [{"rule_id": rule_id, "problems": problems}
                        for rule_id, problems in self.invalid],
            "rules_fired": list(self.rules_fired),
        }


def generate(
    analysis: PortfolioAnalysis,
    *,
    today: date | None = None,
    history: Sequence[DecisionRecord] = (),
    limit: int = DEFAULT_LIMIT,
) -> RecommendationSet:
    """Produce the ranked, gated set of recommendations for one analysis."""
    today = today or analysis.as_of
    context = RuleContext(analysis=analysis, today=today)

    produced: list[Recommendation] = []
    invalid: list[tuple[str, list[str]]] = []
    fired: list[str] = []

    for rule_id, _description, rule_fn in RULES:
        for recommendation in rule_fn(context):
            problems = recommendation.validate()
            if problems:
                invalid.append((rule_id, problems))
                continue
            produced.append(recommendation)
            if rule_id not in fired:
                fired.append(rule_id)

    suppressed: list[Recommendation] = []

    gated: list[Recommendation] = []
    for recommendation in produced:
        verdict = check_suitability(
            analysis.policy, analysis.profile, analysis.portfolio,
            action=recommendation.action.value,
            asset_id=recommendation.subject_id if not recommendation.subject_id.startswith(
                ("class:", "sector:")) else "",
            amount=recommendation.suggested_amount,
            builds_liquidity=recommendation.rule_id == "R-LIQUIDITY",
        )
        if not verdict.allowed:
            recommendation.suppressed_reason = "; ".join(verdict.reasons)
            suppressed.append(recommendation)
            continue
        for warning in verdict.warnings:
            if warning not in recommendation.risks:
                recommendation.risks.append(warning)
        gated.append(recommendation)

    deduped, dropped = _dedupe(gated)
    suppressed.extend(dropped)

    kept, declined = _apply_history(deduped, history)
    suppressed.extend(declined)

    ordered = rank(kept)
    if not ordered:
        ordered = [_do_nothing(analysis, today)]

    return RecommendationSet(
        user_id=analysis.user_id,
        as_of=today,
        recommendations=ordered[:max(limit, 1)] if limit else ordered,
        suppressed=suppressed,
        invalid=invalid,
        rules_fired=fired,
        portfolio_fingerprint=analysis.fingerprint,
    )


def _dedupe(
    recommendations: Sequence[Recommendation],
) -> tuple[list[Recommendation], list[Recommendation]]:
    """One recommendation per subject.

    The winner is the higher priority, then the higher confidence. The loser is
    kept with a reason rather than discarded, because "we also noticed X but
    said Y instead" is exactly the kind of thing an auditor asks about.
    """
    from ..domain import PRIORITY_RANK

    best: dict[str, Recommendation] = {}
    dropped: list[Recommendation] = []
    for recommendation in recommendations:
        key = recommendation.subject_id
        incumbent = best.get(key)
        if incumbent is None:
            best[key] = recommendation
            continue
        challenger_wins = (
            PRIORITY_RANK[recommendation.priority],
            -recommendation.confidence,
        ) < (
            PRIORITY_RANK[incumbent.priority],
            -incumbent.confidence,
        )
        winner, loser = (
            (recommendation, incumbent) if challenger_wins else (incumbent, recommendation)
        )
        loser.suppressed_reason = (
            f"superseded by {winner.rule_id} on the same subject"
        )
        # Carry the loser's finding into the winner rather than losing it. Two
        # rules firing on one holding usually means two true things about it,
        # and the user should see both even though it is one decision.
        note = f"Also flagged: {loser.headline}"
        if note not in winner.reasons:
            winner.reasons.append(note)
        for evidence in loser.evidence:
            if evidence.label not in {e.label for e in winner.evidence}:
                winner.evidence.append(evidence)
        dropped.append(loser)
        best[key] = winner
    return list(best.values()), dropped


def _apply_history(
    recommendations: Sequence[Recommendation], history: Sequence[DecisionRecord]
) -> tuple[list[Recommendation], list[Recommendation]]:
    """Stop repeating a suggestion the user has already turned down.

    Matched on rule and subject rather than on recommendation id, because the
    id changes with the portfolio fingerprint while the suggestion is the same
    one the user already answered.
    """
    declines: dict[str, int] = {}
    for record in history:
        if record.outcome != DecisionOutcome.REJECTED:
            continue
        key = record.recommendation_id
        declines[key] = declines.get(key, 0) + 1

    kept: list[Recommendation] = []
    dropped: list[Recommendation] = []
    for recommendation in recommendations:
        count = declines.get(recommendation.id, 0)
        if count >= DECLINE_TOLERANCE and recommendation.priority != Priority.CRITICAL:
            recommendation.suppressed_reason = (
                f"declined {count} times already; will return if the underlying position "
                "changes materially"
            )
            dropped.append(recommendation)
            continue
        kept.append(recommendation)
    return kept, dropped


def _do_nothing(analysis: PortfolioAnalysis, today: date) -> Recommendation:
    """The valuable non-answer.

    Written as carefully as any other recommendation: it names what was
    checked, so the user can tell the difference between "we looked and it's
    fine" and "we have nothing to say".
    """
    checks = [
        f"Allocation is inside every policy band (largest gap "
        f"{analysis.drift.total_absolute_drift:.1%}).",
        f"No position exceeds the {analysis.policy.max_single_holding:.0%} concentration limit.",
    ]
    if analysis.projections:
        on_track = sum(1 for p in analysis.projections if p.on_track)
        checks.append(f"{on_track} of {len(analysis.projections)} goals are on track.")
    if analysis.profile.annual_expenses:
        checks.append(
            f"Emergency cover is {analysis.profile.emergency_months_covered:.1f} months "
            f"against a {analysis.policy.min_emergency_months}-month minimum."
        )
    checks.append(f"Health score is {analysis.health.score:.0f}/100 ({analysis.health.band}).")

    return Recommendation(
        id=new_id("rec", analysis.user_id, "DO_NOTHING", analysis.fingerprint),
        user_id=analysis.user_id,
        action=Action.DO_NOTHING,
        subject_id="portfolio",
        subject_label="Whole portfolio",
        priority=Priority.LOW,
        confidence=0.9,
        headline="Nothing needs your attention this month",
        reasons=checks,
        evidence=[Evidence(
            "Full portfolio check", tuple(analysis.facts.ids[:8]),
            f"{len(RULES)} rules evaluated against {len(analysis.portfolio.holdings)} holdings",
            "aicio.decisions",
        )],
        portfolio_impact="None. The portfolio is doing what the policy asks of it.",
        risks=[],
        counterarguments=[],
        alternatives=[],
        review_by=today + timedelta(days=30),
        rule_id="R-NONE",
        engine_version=ENGINE_VERSION,
        portfolio_fingerprint=analysis.fingerprint,
    )
