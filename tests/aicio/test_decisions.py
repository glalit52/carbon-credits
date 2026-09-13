"""The decision engine: what it says, and what it refuses to say."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from aicio.analysis import analyse
from aicio.decisions import generate
from aicio.decisions.engine import DECLINE_TOLERANCE, _do_nothing
from aicio.decisions.rules import RULES
from aicio.decisions.scoring import WEIGHTS, priority_for, rank, score
from aicio.domain import (
    Action, DecisionOutcome, DecisionRecord, MATERIAL_ACTIONS, Priority,
)
from aicio.evals.scenarios import build
from aicio.evals.suite import _run
from aicio.ips import check_suitability, generate_policy, horizon_factor


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

def test_policy_follows_capacity_not_appetite(bundle):
    """A client who wants aggressive equity but cannot survive a drawdown gets
    the portfolio they can survive."""
    profile = bundle["profile"]
    assert profile.risk_tolerance > profile.risk_capacity
    assert profile.effective_risk == profile.risk_capacity


def test_policy_targets_sum_to_one(bundle):
    assert sum(band.target for band in bundle["policy"].bands) == pytest.approx(1.0)


def test_a_short_horizon_cuts_equity():
    from aicio.domain import FinancialProfile
    from aicio.money import money

    base = dict(user_id="u", annual_expenses=money(1_200_000), risk_tolerance=7,
                risk_capacity=7)
    long_term = generate_policy(FinancialProfile(**base, horizon_years=25))
    short_term = generate_policy(FinancialProfile(**base, horizon_years=3))
    assert short_term.target(long_term.bands[0].asset_class) < \
        long_term.target(long_term.bands[0].asset_class)


def test_horizon_factor_is_monotonic():
    assert horizon_factor(1) < horizon_factor(4) < horizon_factor(8) <= horizon_factor(30)


def test_the_risk_gap_is_recorded_in_the_policy_notes(bundle):
    assert any("capacity" in note for note in bundle["policy"].notes)


def test_a_near_term_goal_does_not_de_risk_a_retirement_portfolio(bundle):
    """Weighted by goal size, not by which comes first: letting an education
    fee eight years out set the whole horizon is wrong by an order of
    magnitude when retirement is twenty times its size."""
    assert bundle["policy"].horizon_years > 8


# ---------------------------------------------------------------------------
# Suitability
# ---------------------------------------------------------------------------

def test_the_liquidity_gate_does_not_block_building_liquidity():
    """Without this, the liquidity rule blocks itself and the one piece of
    advice the user needs never reaches them."""
    scenario = build("illiquid")
    policy = scenario.resolved_policy()
    blocked = check_suitability(policy, scenario.profile, scenario.portfolio,
                                action="BUY_INCREASE", asset_id="")
    allowed = check_suitability(policy, scenario.profile, scenario.portfolio,
                                action="BUY_INCREASE", builds_liquidity=True)
    assert not blocked.allowed
    assert allowed.allowed


def test_an_exit_from_a_locked_instrument_is_refused():
    scenario = build("locked_in")
    verdict = check_suitability(
        scenario.resolved_policy(), scenario.profile, scenario.portfolio,
        action="EXIT_SWITCH", asset_id="ast_elss",
    )
    assert not verdict.allowed
    assert "lock-in" in verdict.reasons[0]


def test_a_risk_gap_attaches_a_warning_rather_than_blocking(bundle):
    verdict = check_suitability(
        bundle["policy"], bundle["profile"], bundle["portfolio"], action="REDUCE",
    )
    assert verdict.allowed
    assert any("capacity" in w for w in verdict.warnings)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def test_scoring_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_irreversibility_lowers_the_score():
    base = dict(impact=0.8, urgency=0.8, severity=0.8, confidence=0.8, goal_relevance=0.8)
    assert score(**base, irreversible=True).value < score(**base).value


def test_safety_critical_overrides_the_score():
    assert priority_for(0.01, safety_critical=True) is Priority.CRITICAL


def test_ranking_puts_work_above_acknowledgement(recommendations):
    """A HOLD and a REDUCE of equal priority put the HOLD lower: the list is a
    queue of work."""
    from aicio.domain import PRIORITY_RANK
    ordered = rank(recommendations.recommendations)
    ranks = [PRIORITY_RANK[r.priority] for r in ordered]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# Recommendation quality
# ---------------------------------------------------------------------------

def test_every_recommendation_validates(recommendations):
    for item in recommendations.recommendations:
        assert item.validate() == []


def test_material_actions_carry_the_case_against_themselves(recommendations):
    for item in recommendations.recommendations:
        if item.action in MATERIAL_ACTIONS:
            assert item.evidence and item.risks and item.counterarguments
            assert item.review_by is not None


def test_recommendation_ids_are_stable_across_runs(analysis, bundle):
    """Random ids would make every re-run produce 'new' recommendations for an
    unchanged portfolio, which breaks de-duplication and outcome tracking."""
    first = generate(analysis, today=bundle["as_of"], limit=0)
    second = generate(analysis, today=bundle["as_of"], limit=0)
    assert [r.id for r in first.recommendations] == [r.id for r in second.recommendations]


def test_every_recommendation_records_the_engine_that_made_it(recommendations, analysis):
    for item in recommendations.recommendations:
        assert item.engine_version == analysis.engine_version
        assert item.portfolio_fingerprint == analysis.fingerprint


def test_no_rule_produces_an_invalid_recommendation(recommendations):
    assert recommendations.invalid == []


def test_rules_are_uniquely_identified():
    ids = [rule_id for rule_id, _, _ in RULES]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Behaviour of the set
# ---------------------------------------------------------------------------

def test_one_recommendation_per_subject(recommendations):
    subjects = [r.subject_id for r in recommendations.recommendations]
    assert len(subjects) == len(set(subjects))


def test_a_superseded_finding_is_merged_rather_than_lost(recommendations):
    """Two rules firing on one holding usually means two true things about it."""
    superseded = [r for r in recommendations.suppressed if "superseded" in r.suppressed_reason]
    if superseded:
        winner = next(r for r in recommendations.recommendations
                      if r.subject_id == superseded[0].subject_id)
        assert any("Also flagged" in reason for reason in winner.reasons)


def test_a_clean_portfolio_produces_do_nothing():
    analysis, result = _run(build("balanced"))
    assert not [r for r in result.recommendations if r.action in MATERIAL_ACTIONS]


def test_do_nothing_names_what_was_checked():
    analysis, _ = _run(build("balanced"))
    nothing = _do_nothing(analysis, analysis.as_of)
    assert nothing.action is Action.DO_NOTHING
    assert len(nothing.reasons) >= 3
    assert nothing.validate() == []


def test_a_repeatedly_declined_suggestion_stops_being_shown(analysis, bundle):
    first = generate(analysis, today=bundle["as_of"], limit=0)
    target = first.recommendations[0]
    history = [
        DecisionRecord(id=f"d{i}", user_id=analysis.user_id, recommendation_id=target.id,
                       outcome=DecisionOutcome.REJECTED)
        for i in range(DECLINE_TOLERANCE)
    ]
    second = generate(analysis, today=bundle["as_of"], history=history, limit=0)
    assert target.id not in {r.id for r in second.recommendations}
    assert any("declined" in r.suppressed_reason for r in second.suppressed)


def test_a_critical_item_is_never_silenced_by_history():
    scenario = build("illiquid")
    analysis, first = _run(scenario)
    critical = [r for r in first.recommendations if r.priority is Priority.CRITICAL]
    if not critical:
        pytest.skip("this scenario produced no critical item")
    history = [
        DecisionRecord(id=f"d{i}", user_id=analysis.user_id,
                       recommendation_id=critical[0].id, outcome=DecisionOutcome.REJECTED)
        for i in range(DECLINE_TOLERANCE + 2)
    ]
    again = generate(analysis, today=analysis.as_of, history=history, limit=0)
    assert critical[0].id in {r.id for r in again.recommendations}


def test_allocation_drift_produces_one_item_not_four(recommendations):
    """Being overweight equity is being underweight debt; listing it once per
    class turns one decision into four and buries everything else."""
    drift_items = [r for r in recommendations.recommendations if r.rule_id == "R-ALLOC-DRIFT"]
    assert len(drift_items) <= 1


def test_cash_drift_is_left_to_the_liquidity_rules(recommendations):
    for item in recommendations.recommendations:
        if item.rule_id == "R-ALLOC-DRIFT":
            assert "cash" not in item.subject_id
