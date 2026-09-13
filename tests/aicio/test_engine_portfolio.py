"""Allocation, look-through, tax lots and goals."""

from __future__ import annotations

from datetime import date

import pytest

from aicio.domain import (
    Asset, AssetClass, AssetType, Goal, GoalType, Transaction, TxnType,
)
from aicio.engine.allocation import (
    allocation_breakdown, concentration, drift_report, liquid_months, liquid_value,
    rebalance_plan,
)
from aicio.engine.goals import (
    DEFAULT_CMA, future_value, project_goal, required_contribution, simulate_goal,
)
from aicio.engine.taxlots import (
    GainType, INDIA_FY2526, build_lots, classify, exit_tax_cost, realised_gains,
    tax_summary, unrealised_gains,
)
from aicio.engine.xray import fund_overlap, look_through, single_name_breaches
from aicio.money import money, quantity


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------

def test_hybrid_funds_split_across_classes(bundle):
    """A balanced fund at 65% equity must count as 65% equity, not 100%.

    Counting it wherever the fund house filed it is how a portfolio ends up
    twenty points more aggressive than its owner believes.
    """
    hybrid = Asset(id="h", name="Balanced", asset_type=AssetType.HYBRID_FUND,
                   equity_share=0.65)
    split = hybrid.class_split()
    assert split[AssetClass.EQUITY] == pytest.approx(0.65)
    assert split[AssetClass.DEBT] == pytest.approx(0.35)


def test_allocation_weights_sum_to_one(analysis):
    assert sum(analysis.breakdown.weights.values()) == pytest.approx(1.0)


def test_drift_measures_from_the_band_not_the_target(analysis):
    for item in analysis.drift.drifts:
        if item.lower <= item.actual <= item.upper:
            assert item.in_band and item.breach == 0.0
        else:
            assert not item.in_band and item.breach != 0.0


def test_total_drift_is_halved_to_avoid_double_counting(analysis):
    raw = sum(abs(d.gap) for d in analysis.drift.drifts)
    assert analysis.drift.total_absolute_drift == pytest.approx(raw / 2)


def test_rebalance_moves_to_the_band_edge_not_the_midpoint(analysis):
    """Trading to the target costs more and buys nothing the policy asked for."""
    for move in rebalance_plan(analysis.drift):
        drift = next(d for d in analysis.drift.drifts
                     if d.asset_class.value == move["asset_class"])
        edge = drift.lower if drift.actual < drift.lower else drift.upper
        assert move["to_weight"] == pytest.approx(edge, abs=1e-6)


def test_effective_positions_is_the_reciprocal_of_hhi(analysis):
    assert analysis.concentration.effective_positions == pytest.approx(
        1 / analysis.concentration.hhi
    )


def test_concentration_denominator_includes_cash(bundle):
    """Otherwise a weight here disagrees with the same weight on the dashboard,
    and a product whose two screens differ has lost the argument about trust."""
    portfolio = bundle["portfolio"]
    result = concentration(portfolio)
    total = float(portfolio.market_value) + float(portfolio.cash)
    largest = max(float(h.market_value) for h in portfolio.holdings)
    assert result.top[0][2] == pytest.approx(largest / total)


def test_liquid_value_excludes_short_duration_debt(bundle):
    """"Usually accessible" is not what an emergency fund is."""
    portfolio = bundle["portfolio"]
    assert liquid_value(portfolio) == pytest.approx(float(portfolio.cash))
    assert liquid_months(portfolio, 0) is None


# ---------------------------------------------------------------------------
# X-ray
# ---------------------------------------------------------------------------

def test_look_through_finds_exposure_no_holdings_screen_shows(analysis):
    """The demo user owns HDFC Bank directly and through four funds."""
    top = analysis.xray.by_company[0]
    assert top.key == "HDFCBANK"
    assert len(top.contributors) >= 4


def test_look_through_reports_its_own_blind_spot(analysis):
    assert 0 < analysis.xray.coverage < 1
    assert analysis.xray.unresolved_value > 0


def test_overlap_is_measured_against_disclosed_weight():
    """Two identical funds must score 100%, not 35%, just because factsheets
    publish only the top ten holdings."""
    weights = {"A": 0.10, "B": 0.09, "C": 0.08}
    left = Asset(id="l", name="Left", asset_type=AssetType.EQUITY_FUND,
                 holdings_lookthrough=weights)
    right = Asset(id="r", name="Right", asset_type=AssetType.EQUITY_FUND,
                  holdings_lookthrough=dict(weights))
    result = fund_overlap(left, right)
    assert result.overlap == pytest.approx(1.0)
    assert result.absolute_overlap == pytest.approx(0.27)


def test_no_overlap_between_disjoint_funds():
    left = Asset(id="l", name="L", asset_type=AssetType.EQUITY_FUND,
                 holdings_lookthrough={"A": 0.2})
    right = Asset(id="r", name="R", asset_type=AssetType.EQUITY_FUND,
                  holdings_lookthrough={"Z": 0.2})
    assert fund_overlap(left, right).overlap == 0.0


def test_provident_fund_is_not_a_company_exposure(analysis):
    """EPF at 9% of a portfolio must not be reported as the user's largest
    holding in a business."""
    assert all("EPF" not in exposure.key.upper() for exposure in analysis.xray.by_company)


def test_single_name_breaches_use_look_through(analysis):
    breaches = single_name_breaches(analysis.xray, limit=0.05)
    assert breaches and breaches[0].key == "HDFCBANK"
    assert len(breaches[0].through) > 1


# ---------------------------------------------------------------------------
# Tax lots
# ---------------------------------------------------------------------------

def _txn(txn_id, txn_type, on, units, price):
    return Transaction(
        id=txn_id, account_id="acc", asset_id="ast", txn_type=txn_type,
        trade_date=on, units=quantity(units), price=money(price),
        amount=money(units * price),
    )


def test_lots_are_consumed_first_in_first_out():
    """FIFO is the statutory method in India, so it is not a choice."""
    lots, gains = build_lots([
        _txn("t1", TxnType.BUY, date(2023, 1, 1), 100, 10),
        _txn("t2", TxnType.BUY, date(2024, 1, 1), 100, 20),
        _txn("t3", TxnType.SELL, date(2025, 1, 1), 150, 30),
    ])
    assert [g.units for g in gains] == [quantity(100), quantity(50)]
    assert gains[0].acquired_on == date(2023, 1, 1)     # oldest lot goes first
    assert sum(float(lot.open_units) for lot in lots) == pytest.approx(50)


def test_a_split_rescales_lots_without_restarting_the_holding_period():
    lots, _ = build_lots([
        _txn("t1", TxnType.BUY, date(2023, 1, 1), 100, 10),
        _txn("t2", TxnType.SPLIT, date(2024, 1, 1), 2, 0),
    ])
    assert float(lots[0].units) == pytest.approx(200)
    assert float(lots[0].cost_per_unit) == pytest.approx(5)
    assert lots[0].acquired_on == date(2023, 1, 1)


def test_bonus_units_open_a_zero_cost_lot():
    lots, _ = build_lots([
        _txn("t1", TxnType.BUY, date(2023, 1, 1), 100, 10),
        _txn("t2", TxnType.BONUS, date(2024, 1, 1), 20, 0),
    ])
    assert float(lots[1].cost_per_unit) == 0.0


def test_selling_more_than_was_bought_is_flagged_not_invented():
    """Recording a zero-cost lot would invent a gain; the shortfall stays
    visible instead."""
    _, gains = build_lots([
        _txn("t1", TxnType.BUY, date(2023, 1, 1), 50, 10),
        _txn("t2", TxnType.SELL, date(2024, 1, 1), 100, 20),
    ])
    assert any(g.lot_id == "unmatched" for g in gains)


def test_equity_turns_long_term_after_twelve_months():
    asset = Asset(id="a", name="Fund", asset_type=AssetType.EQUITY_FUND)
    assert classify(asset, date(2024, 1, 1), date(2024, 10, 1), INDIA_FY2526) \
        is GainType.SHORT_TERM
    assert classify(asset, date(2024, 1, 1), date(2025, 6, 1), INDIA_FY2526) \
        is GainType.LONG_TERM


def test_debt_funds_bought_after_april_2023_are_taxed_at_slab():
    """The rule turns on the acquisition date, not the disposal date -- a
    detail worth a factor of two to a 30% taxpayer."""
    asset = Asset(id="d", name="Debt", asset_type=AssetType.DEBT_FUND)
    assert classify(asset, date(2023, 6, 1), date(2030, 1, 1), INDIA_FY2526) \
        is GainType.SLAB
    assert classify(asset, date(2022, 6, 1), date(2030, 1, 1), INDIA_FY2526) \
        is GainType.LONG_TERM


def test_ltcg_exemption_is_applied_before_tax():
    asset = Asset(id="a", name="Fund", asset_type=AssetType.EQUITY_FUND)
    gains = realised_gains([
        _txn("t1", TxnType.BUY, date(2023, 1, 1), 1000, 100),
        _txn("t2", TxnType.SELL, date(2025, 1, 1), 1000, 200),
    ], asset)
    summary = tax_summary(gains, [], marginal_rate=0.30)
    # ₹100,000 of long-term gain sits entirely inside the ₹1.25L exemption.
    assert float(summary.realised_long_term) == pytest.approx(100_000)
    assert float(summary.estimated_tax) == pytest.approx(0.0)
    assert float(summary.ltcg_exemption_left) == pytest.approx(25_000)


def test_exit_cost_uses_the_exemption_once():
    asset = Asset(id="a", name="Fund", asset_type=AssetType.EQUITY_FUND)
    lots, _ = build_lots([_txn("t1", TxnType.BUY, date(2023, 1, 1), 1000, 100)])
    positions = unrealised_gains(lots, asset, money(300), on=date(2026, 1, 1))
    cost = exit_tax_cost(positions, marginal_rate=0.30)
    # ₹200,000 gain, less the ₹125,000 exemption, at 12.5%.
    assert float(cost) == pytest.approx(75_000 * 0.125)


def test_near_long_term_lots_are_surfaced():
    asset = Asset(id="a", name="Fund", asset_type=AssetType.EQUITY_FUND)
    lots, _ = build_lots([_txn("t1", TxnType.BUY, date(2025, 9, 1), 100, 100)])
    positions = unrealised_gains(lots, asset, money(150), on=date(2026, 8, 1))
    summary = tax_summary([], positions, marginal_rate=0.30)
    assert summary.near_long_term
    assert 0 < summary.near_long_term[0].days_to_long_term <= 60


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

def test_future_value_treats_contributions_as_start_of_month():
    """A SIP mandate debits at the start of the period, which is one extra
    month of growth on every instalment."""
    without = 100_000 * (1.01 ** 12)
    value = future_value(100_000, 10_000, (1.01 ** 12) - 1, 1)
    assert value > without + 120_000


def test_required_contribution_is_zero_when_already_funded():
    assert required_contribution(100_000, 200_000, 0.08, 5) == 0.0


def test_required_contribution_closes_the_gap():
    needed = required_contribution(1_000_000, 100_000, 0.10, 10)
    assert future_value(100_000, needed, 0.10, 10) == pytest.approx(1_000_000, rel=1e-3)


def test_simulation_is_seeded_and_reproducible():
    args = dict(present=1e6, monthly=10_000, annual_return=0.10, annual_volatility=0.15,
                years=10, target=3e6, trials=300)
    first = simulate_goal(**args)
    second = simulate_goal(**args)
    assert first == second


def test_more_volatility_widens_the_range_and_lowers_the_median():
    """Volatility drag, and the reason a single projected number is a lie.

    Both portfolios have the same 10% expected return. The volatile one has a
    far wider range *and* a materially lower median, because the simulation
    calibrates the mean rather than the median. Half of all outcomes fall below
    the number a deterministic projection would have shown.
    """
    base = dict(present=1e6, monthly=0.0, annual_return=0.10, years=10,
                target=2e6, trials=800)
    calm, calm_probability = simulate_goal(**base, annual_volatility=0.02)
    wild, wild_probability = simulate_goal(**base, annual_volatility=0.30)
    assert (wild["p90"] - wild["p10"]) > (calm["p90"] - calm["p10"]) * 3
    assert wild["p50"] < calm["p50"] * 0.8
    assert wild_probability < calm_probability


def test_goal_target_is_inflated_to_the_target_date():
    goal = Goal(id="g", user_id="u", name="School", goal_type=GoalType.EDUCATION,
                target_amount=money(1_000_000), target_date=date(2036, 9, 12),
                inflation_rate=0.06)
    projection = project_goal(goal, current_value=0, monthly_contribution=1000,
                              weights={AssetClass.DEBT: 1.0}, today=date(2026, 9, 12),
                              trials=200)
    assert projection.target_nominal == pytest.approx(1_000_000 * 1.06 ** 10, rel=0.01)


def test_correlated_volatility_sits_between_the_naive_extremes():
    weights = {AssetClass.EQUITY: 0.6, AssetClass.DEBT: 0.4}
    correlated = DEFAULT_CMA.portfolio_volatility(weights)
    naive_sum = 0.6 * DEFAULT_CMA.volatility[AssetClass.EQUITY] + \
        0.4 * DEFAULT_CMA.volatility[AssetClass.DEBT]
    independent = (
        (0.6 * DEFAULT_CMA.volatility[AssetClass.EQUITY]) ** 2
        + (0.4 * DEFAULT_CMA.volatility[AssetClass.DEBT]) ** 2
    ) ** 0.5
    assert independent < correlated < naive_sum
