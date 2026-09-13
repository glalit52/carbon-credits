"""The Wealth Health Score.

A single number is a blunt instrument, and the temptation with one is to tune
it until it looks encouraging. Two design choices push against that:

*   The score is the weighted mean of eight *independently defensible*
    dimensions, each of which is reported with its own score, its own inputs
    and a sentence saying what moved it. The headline is a summary of the
    detail, never a replacement for it.
*   Dimensions with no data score ``None`` and are dropped from the weighting
    rather than scoring zero or a charitable 50. A user with no goals set
    should not be told their goal alignment is poor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .allocation import AllocationBreakdown, Concentration, DriftReport
from .goals import GoalProjection
from .xray import Overlap, XRay


@dataclass
class Dimension:
    key: str
    label: str
    score: float | None                   # 0-100, None when not assessable
    weight: float
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label,
            "score": None if self.score is None else round(self.score, 1),
            "weight": self.weight, "summary": self.summary, "detail": self.detail,
        }


@dataclass
class HealthScore:
    score: float
    band: str
    dimensions: list[Dimension]
    #: Dimensions that could not be assessed, so the user knows the score is
    #: partial rather than flattering.
    unassessed: list[str] = field(default_factory=list)

    def dimension(self, key: str) -> Dimension | None:
        for item in self.dimensions:
            if item.key == key:
                return item
        return None

    @property
    def weakest(self) -> Dimension | None:
        scored = [d for d in self.dimensions if d.score is not None]
        return min(scored, key=lambda d: d.score) if scored else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "band": self.band,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "unassessed": list(self.unassessed),
        }


def _band(score: float) -> str:
    if score >= 80:
        return "strong"
    if score >= 65:
        return "sound"
    if score >= 50:
        return "needs attention"
    return "fragile"


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def health_score(
    *,
    breakdown: AllocationBreakdown,
    drift: DriftReport,
    concentration_: Concentration,
    xray: XRay | None = None,
    overlaps: Sequence[Overlap] = (),
    projections: Sequence[GoalProjection] = (),
    emergency_months: float | None = None,
    required_emergency_months: int = 6,
    unrealised_short_term_share: float | None = None,
    stale_holding_share: float = 0.0,
    quality_scores: Sequence[float] = (),
    behaviour: dict[str, float] | None = None,
    max_single_holding: float = 0.10,
    max_sector: float = 0.30,
    overlap_exposure: float = 0.0,
    single_name_top: float = 0.0,
) -> HealthScore:
    """Score the eight dimensions the PRD names, then combine them."""
    dimensions: list[Dimension] = []

    # --- Diversification ---------------------------------------------------
    effective = concentration_.effective_positions
    # 15 effective positions is a genuinely diversified retail portfolio -- not
    # an institutional 40, which no individual reaches and which would score
    # every real user as a failure.
    div_score = _clamp(100 * min(1.0, effective / 15) ** 0.7)
    worst_overlap = max((o.overlap for o in overlaps), default=0.0)
    # Scaled by how much of the portfolio the overlapping pair actually is:
    # two identical funds holding 2% between them is a tidiness issue, not a
    # diversification failure.
    div_score -= min(25.0, worst_overlap * max(0.0, min(1.0, overlap_exposure)) * 60)
    # "Diversified" and "cash" are bookkeeping buckets rather than sectors; a
    # broad equity fund landing in the first must not read as a sector bet.
    real_sectors = [
        e for e in (xray.by_sector if xray else []) if e.key not in {"diversified", "cash"}
    ]
    sector_top = real_sectors[0].weight if real_sectors else 0.0
    if sector_top > max_sector:
        div_score -= min(20.0, (sector_top - max_sector) * 100)
    div_score = _clamp(div_score)
    dimensions.append(Dimension(
        "diversification", "Diversification", div_score, 0.16,
        f"{effective:.1f} effective positions"
        + (f"; worst fund overlap {worst_overlap:.0%}" if worst_overlap else "")
        + (f"; largest sector {sector_top:.0%}" if sector_top else ""),
        {"effective_positions": round(effective, 2), "hhi": round(concentration_.hhi, 6),
         "worst_overlap": round(worst_overlap, 4), "top_sector_weight": round(sector_top, 4)},
    ))

    # --- Concentration risk (position level) -------------------------------
    # Measured on look-through single names, not on fund positions: four
    # diversified funds are not a concentration risk however large each is.
    top_position = concentration_.top[0][2] if concentration_.top else 0.0
    conc_score = _clamp(
        100 - max(0.0, single_name_top - max_single_holding) * 400
        - max(0.0, top_position - 0.35) * 60
    )
    dimensions.append(Dimension(
        "risk", "Risk concentration", conc_score, 0.16,
        f"Largest single company {single_name_top:.1%} against a {max_single_holding:.0%} "
        f"limit; largest fund position {top_position:.1%}",
        {"single_name_top": round(single_name_top, 4),
         "top_position": round(top_position, 4)},
    ))

    # --- Allocation --------------------------------------------------------
    total_drift = drift.total_absolute_drift
    # 10 points of drift costs 18 points of score; 30 points costs 54. Steep
    # enough to matter, shallow enough that a portfolio mid-rebalance is not
    # scored as a catastrophe.
    alloc_score = _clamp(100 - total_drift * 180)
    if drift.breaches:
        alloc_score = min(alloc_score, 70.0)
    dimensions.append(Dimension(
        "allocation", "Allocation discipline", alloc_score, 0.14,
        f"{total_drift:.1%} away from policy"
        + (f"; {len(drift.breaches)} class(es) outside their band" if drift.breaches else ""),
        {"total_absolute_drift": round(total_drift, 4),
         "breaches": [d.asset_class.value for d in drift.breaches]},
    ))

    # --- Investment quality ------------------------------------------------
    if quality_scores:
        quality = sum(quality_scores) / len(quality_scores)
        dimensions.append(Dimension(
            "quality", "Investment quality", _clamp(quality), 0.14,
            f"Mean holding quality {quality:.0f}/100 across {len(quality_scores)} assessed holdings",
            {"assessed": len(quality_scores)},
        ))
    else:
        dimensions.append(Dimension(
            "quality", "Investment quality", None, 0.14,
            "No fund or stock evidence available yet", {},
        ))

    # --- Liquidity ---------------------------------------------------------
    if emergency_months is None:
        dimensions.append(Dimension(
            "liquidity", "Liquidity", None, 0.12,
            "Monthly expenses not captured, so cover cannot be assessed", {},
        ))
    else:
        ratio = emergency_months / max(1, required_emergency_months)
        liq_score = _clamp(100 * min(1.0, ratio) ** 0.8 if ratio < 1 else min(100.0, 90 + ratio * 5))
        dimensions.append(Dimension(
            "liquidity", "Liquidity", liq_score, 0.12,
            f"{emergency_months:.1f} months of expenses covered "
            f"against a {required_emergency_months}-month policy minimum",
            {"months": round(emergency_months, 2), "required": required_emergency_months},
        ))

    # --- Tax efficiency ----------------------------------------------------
    if unrealised_short_term_share is None:
        dimensions.append(Dimension(
            "tax", "Tax efficiency", None, 0.10,
            "Purchase history is incomplete, so tax position cannot be assessed", {},
        ))
    else:
        tax_score = _clamp(100 - unrealised_short_term_share * 70)
        dimensions.append(Dimension(
            "tax", "Tax efficiency", tax_score, 0.10,
            f"{unrealised_short_term_share:.0%} of unrealised gains are still short-term",
            {"short_term_share": round(unrealised_short_term_share, 4)},
        ))

    # --- Goal alignment ----------------------------------------------------
    if projections:
        # Weighted by goal priority: missing the retirement number matters more
        # than missing the holiday.
        weights = [1.0 / max(1, index + 1) for index in range(len(projections))]
        goal_score = sum(p.probability * 100 * w for p, w in zip(projections, weights)) / sum(weights)
        off = [p.goal_name for p in projections if not p.on_track]
        dimensions.append(Dimension(
            "goals", "Goal alignment", _clamp(goal_score), 0.12,
            f"{len(projections) - len(off)} of {len(projections)} goals on track"
            + (f"; at risk: {', '.join(off[:3])}" if off else ""),
            {"off_track": off},
        ))
    else:
        dimensions.append(Dimension(
            "goals", "Goal alignment", None, 0.12,
            "No goals defined yet", {},
        ))

    # --- Behaviour ---------------------------------------------------------
    behaviour = behaviour or {}
    behave_score = 100.0
    notes: list[str] = []
    churn = behaviour.get("annual_turnover")
    if churn is not None:
        behave_score -= min(30.0, max(0.0, churn - 0.3) * 60)
        notes.append(f"turnover {churn:.0%}")
    since_review = behaviour.get("months_since_review")
    if since_review is not None:
        behave_score -= min(25.0, max(0.0, since_review - 6) * 4)
        notes.append(f"{since_review:.0f} months since last review")
    ignored = behaviour.get("ignored_high_priority")
    if ignored:
        behave_score -= min(20.0, ignored * 7)
        notes.append(f"{int(ignored)} high-priority items left unread")
    if stale_holding_share:
        behave_score -= min(20.0, stale_holding_share * 40)
        notes.append(f"{stale_holding_share:.0%} of holdings not refreshed recently")
    dimensions.append(Dimension(
        "behaviour", "Behaviour", _clamp(behave_score) if (behaviour or stale_holding_share) else None,
        0.06,
        "; ".join(notes) if notes else "Not enough decision history yet",
        dict(behaviour),
    ))

    scored = [d for d in dimensions if d.score is not None]
    if not scored:
        return HealthScore(0.0, "unknown", dimensions, [d.key for d in dimensions])
    weight_total = sum(d.weight for d in scored)
    overall = sum(d.score * d.weight for d in scored) / weight_total
    return HealthScore(
        score=round(overall, 1),
        band=_band(overall),
        dimensions=dimensions,
        unassessed=[d.key for d in dimensions if d.score is None],
    )


def fund_quality_score(
    *,
    excess_return_vs_benchmark: float | None = None,
    rolling_win_rate: float | None = None,
    expense_ratio: float | None = None,
    category_expense_median: float = 0.011,
    manager_changed_recently: bool = False,
    style_drift: float | None = None,
    max_drawdown_vs_category: float | None = None,
) -> float:
    """Quality of one fund, 0-100, from evidence rather than star ratings.

    Starts at a neutral 60 and moves on evidence. A fund with no evidence
    available stays at 60 rather than being scored well or badly, which keeps
    "we don't know" distinguishable from "it's average".
    """
    score = 60.0
    if excess_return_vs_benchmark is not None:
        score += max(-25.0, min(25.0, excess_return_vs_benchmark * 400))
    if rolling_win_rate is not None:
        score += (rolling_win_rate - 0.5) * 40
    if expense_ratio is not None:
        score -= min(15.0, max(-5.0, (expense_ratio - category_expense_median) * 1200))
    if manager_changed_recently:
        # Not a verdict -- a reason to look. A manager change resets the
        # relevance of the track record, which is what the score reflects.
        score -= 8.0
    if style_drift is not None:
        score -= min(15.0, style_drift * 30)
    if max_drawdown_vs_category is not None:
        score -= min(15.0, max(0.0, max_drawdown_vs_category) * 100)
    return _clamp(score)
