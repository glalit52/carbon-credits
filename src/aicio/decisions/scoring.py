"""Ranking: which of a dozen true things to show first.

The hardest problem in the product is not finding issues -- a real portfolio
has plenty -- it is deciding that eleven of them can wait. The score below
combines the five things that actually determine whether an item deserves a
user's attention today, and the weights are stated here rather than tuned into
opacity elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..domain import Action, Priority, Recommendation

#: Weights sum to 1. Impact leads because the product's promise is that what
#: it shows is worth the user's time; reversibility is negative because an
#: action that cannot be undone should need a higher bar, not a lower one.
WEIGHTS = {
    "impact": 0.34,        # how much money or goal probability is at stake
    "urgency": 0.22,       # does waiting a month make it worse
    "severity": 0.20,      # how far outside policy the state is
    "confidence": 0.16,    # how sure the engine is
    "goal_relevance": 0.08,
}
IRREVERSIBILITY_PENALTY = 0.12


@dataclass(frozen=True)
class Score:
    value: float
    impact: float
    urgency: float
    severity: float
    confidence: float
    goal_relevance: float
    irreversible: bool

    def to_dict(self) -> dict[str, float | bool]:
        return {
            "value": round(self.value, 4), "impact": round(self.impact, 4),
            "urgency": round(self.urgency, 4), "severity": round(self.severity, 4),
            "confidence": round(self.confidence, 4),
            "goal_relevance": round(self.goal_relevance, 4),
            "irreversible": self.irreversible,
        }


def score(
    *,
    impact: float,
    urgency: float = 0.5,
    severity: float = 0.5,
    confidence: float = 0.7,
    goal_relevance: float = 0.3,
    irreversible: bool = False,
) -> Score:
    raw = (
        WEIGHTS["impact"] * _clamp(impact)
        + WEIGHTS["urgency"] * _clamp(urgency)
        + WEIGHTS["severity"] * _clamp(severity)
        + WEIGHTS["confidence"] * _clamp(confidence)
        + WEIGHTS["goal_relevance"] * _clamp(goal_relevance)
    )
    if irreversible:
        raw -= IRREVERSIBILITY_PENALTY
    return Score(_clamp(raw), impact, urgency, severity, confidence, goal_relevance, irreversible)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def priority_for(value: float, *, safety_critical: bool = False) -> Priority:
    """Map a score to a priority band.

    ``safety_critical`` exists for the small set of conditions -- a suspected
    data anomaly, a liquidity breach -- that must reach the user regardless of
    how their score happens to land.
    """
    if safety_critical:
        return Priority.CRITICAL
    if value >= 0.72:
        return Priority.HIGH
    if value >= 0.48:
        return Priority.MEDIUM
    return Priority.LOW


def rank(recommendations: Sequence[Recommendation]) -> list[Recommendation]:
    """Order for display: priority first, then confidence, then materiality.

    Ties break towards the action that asks less of the user, so a HOLD and a
    REDUCE of equal priority put the HOLD lower -- the list is meant to be a
    queue of work, and work belongs at the top.
    """
    action_rank = {
        Action.EXIT_SWITCH: 0, Action.REDUCE: 1, Action.BUY_INCREASE: 2,
        Action.REVIEW: 3, Action.HOLD: 4, Action.DO_NOTHING: 5,
    }
    from ..domain import PRIORITY_RANK
    return sorted(
        recommendations,
        key=lambda r: (
            PRIORITY_RANK[r.priority],
            -r.confidence,
            action_rank.get(r.action, 9),
            r.subject_label,
        ),
    )
