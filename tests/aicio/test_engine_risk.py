"""Risk measures and scenario tests."""

from __future__ import annotations

import math

import pytest

from aicio.engine.risk import (
    RiskError, STANDARD_SHOCKS, Shock, beta, downside_deviation, drawdown_series,
    historical_var, max_drawdown, risk_capacity_score, run_scenarios, scenario_test,
    sharpe, sortino, volatility,
)


def test_volatility_is_the_sample_standard_deviation_annualised():
    returns = [0.01, -0.01] * 10
    expected = math.sqrt(sum(r ** 2 for r in returns) / (len(returns) - 1)) * math.sqrt(252)
    assert volatility(returns) == pytest.approx(expected)


def test_volatility_needs_two_points():
    with pytest.raises(RiskError):
        volatility([0.01])


def test_downside_deviation_ignores_upside():
    """Upside surprise is not risk; a series that only rises must score zero."""
    assert downside_deviation([0.02, 0.03, 0.01]) == pytest.approx(0.0)


def test_max_drawdown_finds_depth_and_recovery():
    result = max_drawdown([100, 110, 95, 80, 90, 120, 118])
    assert result.depth == pytest.approx(-0.272727, abs=1e-5)
    assert result.peak_index == 1
    assert result.trough_index == 3
    assert result.recovered


def test_drawdown_still_under_water_reports_no_recovery():
    result = max_drawdown([100, 120, 80, 85, 90])
    assert result.depth == pytest.approx(-1 / 3, abs=1e-6)
    assert not result.recovered


def test_drawdown_series_tracks_the_running_peak():
    assert drawdown_series([100, 90, 120, 60]) == pytest.approx([0.0, -0.1, 0.0, -0.5])


def test_sharpe_and_sortino_are_undefined_rather_than_zero():
    with pytest.raises(RiskError):
        sharpe([0.01] * 10)
    with pytest.raises(RiskError):
        sortino([0.01] * 10, risk_free=0.0)


def test_sortino_exceeds_sharpe_when_downside_is_mild():
    returns = [0.02, 0.02, 0.02, -0.005, 0.02, 0.02, -0.005, 0.02] * 4
    assert sortino(returns) > sharpe(returns)


def test_beta_against_a_flat_market_is_undefined():
    with pytest.raises(RiskError):
        beta([0.01, -0.01], [0.0, 0.0])


def test_beta_of_a_doubled_series_is_two():
    market = [0.01, -0.02, 0.015, -0.005, 0.02]
    assert beta([2 * r for r in market], market) == pytest.approx(2.0)


def test_var_needs_enough_observations_to_mean_anything():
    with pytest.raises(RiskError):
        historical_var([0.01, -0.02, 0.0])


def test_scenario_applies_the_shock_per_asset_class():
    result = scenario_test(
        {"equity": 7_000_000, "debt": 2_000_000, "cash": 1_000_000},
        Shock("test", {"equity": -0.50}),
        monthly_expenses=100_000,
    )
    assert result.value_after == pytest.approx(6_500_000)
    assert result.loss_pct == pytest.approx(-0.35)
    # Debt and cash are untouched, so liquidity is unchanged.
    assert result.liquidity_months_after == pytest.approx(30.0)


def test_scenario_carries_the_shock_it_applied():
    result = scenario_test({"equity": 100}, STANDARD_SHOCKS[2])
    assert result.moves["equity"] == pytest.approx(-0.50)


def test_standard_battery_covers_the_prd_shocks():
    names = {shock.name for shock in STANDARD_SHOCKS}
    assert {"equity_-20", "equity_-30", "equity_-50"} <= names
    assert len(run_scenarios({"equity": 100.0})) == len(STANDARD_SHOCKS)


def test_risk_capacity_falls_with_dependents_and_debt():
    stable = dict(horizon_years=20, income_stability="stable", dependents=0,
                  emergency_months=8, debt_to_income=0.1)
    assert risk_capacity_score(**stable) > risk_capacity_score(
        **{**stable, "dependents": 3, "debt_to_income": 0.8,
           "income_stability": "concentrated", "emergency_months": 1}
    )


def test_risk_capacity_stays_on_the_one_to_ten_scale():
    extreme = risk_capacity_score(horizon_years=90, income_stability="stable",
                                  dependents=0, emergency_months=60, debt_to_income=0.0)
    assert 1 <= extreme <= 10
