"""Forward delivery, and the volume it is safe to promise.

The rest of the package answers "how many credits does this vintage carry".
These tests pin the other question -- how much can be sold forward without
having to buy the shortfall back -- and in particular pin that the answer is
read off the *lower* tail. Reading the upper one is the mistake that turns a
carbon developer into a short position.
"""

import pytest

from carbonstack import forecast as F
from carbonstack.cli import main


def trees(years=range(2027, 2035), start=20.0, step=6.0, unc=0.30,
          settled_through=2026):
    return [F.VintageProjection(
        year=y, net_t=start + step * (y - min(years)),
        relative_uncertainty=unc, track="agroforestry",
        settled=y <= settled_through) for y in years]


def rice(years=range(2027, 2033), net=1.5, unc=0.35):
    return [F.VintageProjection(year=y, net_t=net, relative_uncertainty=unc,
                                track="rice", settled=False) for y in years]


# --- the direction of the tail ---------------------------------------------

def test_safe_volume_is_the_lower_tail_not_the_upper():
    """The whole point. A forward sold at P90-upside is a short position."""
    f = F.run(trees(), trials=1500)
    assert f.safe_total_t < f.p50_total_t
    assert f.safe_total_t < f.projected_total_t


def test_a_higher_confidence_demands_a_smaller_promise():
    cautious = F.run(trees(), trials=1500, confidence=0.95)
    relaxed = F.run(trees(), trials=1500, confidence=0.60)
    assert cautious.safe_total_t < relaxed.safe_total_t


def test_certainty_is_not_on_offer():
    with pytest.raises(ValueError, match="certainty is not available"):
        F.run(trees(), confidence=1.0)
    with pytest.raises(ValueError, match="not a commitment"):
        F.run(trees(), confidence=0.2)


def test_with_no_risk_the_safe_volume_is_the_projection():
    calm = F.RiskModel(dropout_per_year=0.0, practice_lapse_per_year=0.0,
                       planting_failure_per_year=0.0,
                       verification_slip_per_year=0.0,
                       measurement_sigma_scale=0.0)
    f = F.run(trees(), risk=calm, trials=400)
    assert f.safe_total_t == pytest.approx(f.projected_total_t, rel=1e-9)
    assert f.portfolio_haircut == pytest.approx(0.0)


# --- aggregation ------------------------------------------------------------

def test_aggregation_raises_the_promise_and_then_stops_paying():
    """The case for aggregating smallholders, as a number.

    Attrition and crop failure diversify away across units; verification
    timing and measurement error do not, so the curve flattens rather than
    continuing to climb.
    """
    curve = F.aggregation_curve(trees(), units=(1, 5, 50, 500), trials=800)
    safe = [row["safe_t"] for row in curve]
    assert safe[0] < safe[1] < safe[2]
    early_gain = safe[1] - safe[0]
    late_gain = safe[3] - safe[2]
    assert late_gain < early_gain / 5


def test_a_single_unit_portfolio_carries_a_cliff():
    """One farmer is not a portfolio. When they leave, everything stops."""
    alone = F.run(trees(), risk=F.RiskModel(enrolled_units=1), trials=1500)
    many = F.run(trees(), risk=F.RiskModel(enrolled_units=200), trials=1500)
    assert alone.portfolio_haircut > many.portfolio_haircut + 0.2


# --- the individual risks ---------------------------------------------------

def test_dropout_compounds_across_the_horizon():
    """Once a farmer has left they are gone for every later vintage, so the
    haircut has to widen with time rather than staying flat."""
    f = F.run(trees(), risk=F.RiskModel(enrolled_units=1), trials=2000)
    unsettled = [y for y in f.years if y.projected_t > 0][1:]
    assert unsettled[-1].p50 / unsettled[-1].projected_t < \
        unsettled[0].p50 / unsettled[0].projected_t


def test_a_settled_vintage_carries_no_delivery_risk():
    """The year has closed and the evidence is in. Measurement error still
    applies; a farmer leaving next year does not reach back."""
    only_settled = [F.VintageProjection(year=2025, net_t=50.0,
                                        relative_uncertainty=0.0,
                                        settled=True)]
    f = F.run(only_settled, trials=300)
    assert f.safe_total_t == pytest.approx(50.0)
    assert any("already settled" in w for w in f.warnings)


def test_planting_failure_does_not_apply_to_a_methane_claim():
    """A rice field cannot have its trees die. Charging it for that risk
    would be a deduction with no mechanism behind it."""
    risk = F.RiskModel(planting_failure_per_year=0.9, dropout_per_year=0.0,
                       practice_lapse_per_year=0.0,
                       verification_slip_per_year=0.0,
                       measurement_sigma_scale=0.0)
    f = F.run(rice(), risk=risk, trials=400)
    assert f.safe_total_t == pytest.approx(f.projected_total_t, rel=1e-9)


def test_practice_lapse_does_not_apply_to_a_planting():
    risk = F.RiskModel(practice_lapse_per_year=0.9, dropout_per_year=0.0,
                       planting_failure_per_year=0.0,
                       verification_slip_per_year=0.0,
                       measurement_sigma_scale=0.0)
    f = F.run(trees(settled_through=0), risk=risk, trials=400)
    assert f.safe_total_t == pytest.approx(f.projected_total_t, rel=1e-9)


def test_a_slipped_verification_moves_volume_rather_than_destroying_it():
    """Credits that arrive in March are late, not absent. Only a slip out of
    the final year is a genuine miss."""
    slipping = F.RiskModel(dropout_per_year=0.0, practice_lapse_per_year=0.0,
                           planting_failure_per_year=0.0,
                           verification_slip_per_year=0.5,
                           measurement_sigma_scale=0.0)
    projections = trees(settled_through=0)
    f = F.run(projections, risk=slipping, trials=2000)
    last = f.years[-1].projected_t
    # Everything but the tail year survives somewhere in the horizon.
    assert f.p50_total_t > f.projected_total_t - last * 1.5


def test_the_sensitivity_names_what_is_worth_fixing():
    f = F.run(trees(), risk=F.RiskModel(enrolled_units=1), trials=1200)
    assert set(f.sensitivity) == {
        "farmer dropout", "practice lapse", "planting failure",
        "verification slip", "measurement uncertainty"}
    name, cost = f.dominant_risk
    assert name == "farmer dropout"
    assert cost > 0
    # A risk that cannot apply to this track cannot be the thing to fix.
    assert f.sensitivity["practice lapse"] == pytest.approx(f.safe_total_t)


# --- findings ---------------------------------------------------------------

def test_it_says_when_the_horizon_must_be_sold_as_a_basket():
    """A year-by-year schedule fails on verification timing even when the
    carbon is there. That is a contract problem, not a carbon problem."""
    f = F.run(trees(), risk=F.RiskModel(enrolled_units=30), trials=1500)
    assert any(y.safe_t <= 0 for y in f.years)
    assert f.safe_total_t > 0
    assert any("as a basket" in w for w in f.warnings)


def test_an_empty_forecast_refuses_rather_than_returning_zero():
    f = F.run([], trials=100)
    assert f.safe_total_t == 0.0
    assert any("nothing to forecast" in w for w in f.warnings)


def test_the_report_carries_its_derivation():
    f = F.run(trees(), trials=400)
    report = f.report()
    labels = [t.label for t in report.terms]
    assert "projected delivery" in labels
    assert "portfolio haircut" in labels
    assert any("simulated portfolios" in c for c in report.citations)


def test_the_simulation_is_reproducible():
    """A number in a term sheet has to be rebuildable months later."""
    a = F.run(trees(), trials=600, seed=7)
    b = F.run(trees(), trials=600, seed=7)
    c = F.run(trees(), trials=600, seed=8)
    assert a.safe_total_t == b.safe_total_t
    assert a.safe_total_t != c.safe_total_t


# --- offtake ----------------------------------------------------------------

def test_committing_the_safe_volume_clears_the_confidence_bar():
    projections = trees()
    f = F.run(projections, trials=2000)
    a = F.assess_offtake(f, projections, committed_t=f.safe_total_t,
                         replacement_price=45.0)
    assert a.delivery_probability >= f.confidence - 0.02
    assert "signable" in a.verdict


def test_committing_the_projection_does_not():
    projections = trees()
    f = F.run(projections, trials=2000)
    a = F.assess_offtake(f, projections, committed_t=f.projected_total_t,
                         replacement_price=45.0)
    assert a.delivery_probability < f.confidence
    assert a.expected_shortfall_t > 0
    assert a.expected_cover_cost == pytest.approx(
        a.expected_shortfall_t * 45.0)


def test_an_impossible_commitment_is_refused_in_words():
    projections = trees()
    f = F.run(projections, trials=800)
    a = F.assess_offtake(f, projections,
                         committed_t=f.projected_total_t * 3,
                         replacement_price=45.0)
    assert "do not sign" in a.verdict


# --- adapters and CLI -------------------------------------------------------

def test_stored_vintages_adapt_into_projections():
    rows = [{"year": 2025, "net_t": 1.1, "relative_uncertainty": 0.35,
             "complete": True},
            {"year": 2026, "net_t": 1.4, "relative_uncertainty": 0.35,
             "complete": False}]
    projections = F.from_vintages(rows, track="rice")
    assert [p.settled for p in projections] == [True, False]
    assert all(p.track == "rice" for p in projections)


def test_cli_forecasts_a_pilot_and_tests_an_offtake(capsys):
    assert main(["forecast", "gatugi", "--through", "2032", "--units", "40",
                 "--trials", "400", "--offtake", "200",
                 "--aggregation"]) == 0
    out = capsys.readouterr().out
    assert "safe to sell forward" in out
    assert "what each risk costs in safe volume" in out
    assert "how many units before an offtake is signable" in out
    assert "offtake of 200 tCO2e" in out


def test_cli_forecasts_the_rice_site(capsys):
    assert main(["forecast", "vallam", "--through", "2030",
                 "--trials", "400"]) == 0
    out = capsys.readouterr().out
    assert "forward delivery" in out
    assert "practice lapse" in out
