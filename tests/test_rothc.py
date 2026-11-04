"""RothC-26.3: the model, its initialisation, and what it refuses to claim.

The equations are checked against values that can be computed by hand from
the published guide, and the projection against the two properties that
matter commercially: the steady state really is steady, and a practice the
model cannot see contributes nothing.
"""

import math

import pytest

from carbonstack.connectors.weather import from_normals
from carbonstack.rothc import (
    Management, RothC, apply_practices, co2_fraction, falloon_iom, max_tsmd,
    moisture_modifier, project_soc, temperature_modifier,
)
from carbonstack.sites import NYERI, THANJAVUR


def climate(site=THANJAVUR):
    c = site.climate
    return from_normals(site.lat, site.lon, c.monthly_rain_mm, c.mean_temp_c,
                        c.temp_amplitude_c)


# --- the published modifiers --------------------------------------------------

def test_temperature_modifier_matches_the_guide():
    """a = 47.91 / (1 + e^(106.06 / (T + 18.27))); about 1 near 9-10 C."""
    assert temperature_modifier(10.0) == pytest.approx(
        47.91 / (1 + math.exp(106.06 / 28.27)))
    assert 0.9 < temperature_modifier(9.5) < 1.1
    assert temperature_modifier(-20) == 0.0
    assert temperature_modifier(30) > temperature_modifier(20)


def test_moisture_deficit_and_modifier():
    m = max_tsmd(30.0)
    assert m == pytest.approx(-(20 + 39 - 9))
    assert max_tsmd(30.0, bare=True) == pytest.approx(m / 1.8)
    assert moisture_modifier(0.0, m) == 1.0
    assert moisture_modifier(m, m) == pytest.approx(0.2)


def test_more_clay_keeps_more_carbon():
    assert co2_fraction(40) < co2_fraction(10)


def test_falloon_iom():
    assert falloon_iom(40.0) == pytest.approx(0.049 * 40 ** 1.139)


# --- initialisation -------------------------------------------------------------

def test_the_solved_steady_state_is_actually_steady():
    """The exact solve must agree with what fifty more years of the model do."""
    model = RothC(clay_pct=30)
    normals = climate().months
    base = Management("baseline")
    plant, pools = model.solve_input(normals, base, 32.0)
    assert pools.total == pytest.approx(32.0, abs=1e-6)
    p, acc = pools, 0.0
    for _ in range(50):
        p, acc = model.run_year(p, normals, base, plant, acc)
    assert p.total == pytest.approx(32.0, abs=0.05)


def test_hotter_climate_needs_more_input_to_hold_the_same_stock():
    model = RothC(clay_pct=35)
    hot, _ = model.solve_input(climate(THANJAVUR).months, Management("b"), 40.0)
    cool, _ = model.solve_input(climate(NYERI).months, Management("b"), 40.0)
    assert hot > cool


# --- practices -------------------------------------------------------------------

def test_reduced_tillage_is_refused_rather_than_modelled():
    project, warnings = apply_practices(Management("b"), ["reduced_tillage"])
    assert project.input_multiplier == 1.0 and project.extra_input_t_c_ha == 0.0
    assert any("no tillage term" in w for w in warnings)


def test_cover_crop_covers_the_fallow():
    bare_fallow = Management("b", covered=tuple(m not in (2, 3, 4) for m in range(1, 13)))
    project, _ = apply_practices(bare_fallow, ["cover_crop"], fallow_months=(2, 3, 4))
    assert all(project.covered)


def test_unknown_practice_is_an_error():
    with pytest.raises(ValueError, match="unknown practice"):
        apply_practices(Management("b"), ["biochar_magic"])


# --- projection ------------------------------------------------------------------

def test_projection_gains_carbon_and_reports_a_seeded_interval():
    kw = dict(clay_pct=38, initial_soc_t_c_ha=32, baseline=Management("baseline"),
              practices=["residue_retention"], start_year=2026, horizon=10, draws=60)
    a = project_soc(climate(), **kw)
    b = project_soc(climate(), **kw)
    assert a.delta_t_c_ha[-1] > 0
    assert a.delta_p05[-1] < a.delta_t_c_ha[-1] < a.delta_p95[-1]
    assert a.delta_p95 == b.delta_p95                     # rebuildable
    # Baseline sits at its equilibrium, so it does not drift.
    assert a.baseline_t_c_ha[-1] == pytest.approx(32.0, abs=0.1)


def test_ex_ante_is_charged_for_its_uncertainty():
    r = project_soc(climate(), clay_pct=38, initial_soc_t_c_ha=32,
                    baseline=Management("baseline"), practices=["residue_retention"],
                    start_year=2026, horizon=10, draws=60)
    assert r.relative_uncertainty() > 0.15
    assert r.ex_ante_t_co2e_ha_yr() < r.annual_t_co2e_ha()
    assert "uncertainty deduction" in r.calculation.render()


def test_no_practice_change_is_no_credit():
    r = project_soc(climate(), clay_pct=38, initial_soc_t_c_ha=32,
                    baseline=Management("baseline"), practices=[],
                    start_year=2026, horizon=5, draws=20)
    assert abs(r.delta_t_c_ha[-1]) < 1e-9
    assert r.ex_ante_t_co2e_ha_yr() == 0.0


def test_paddy_months_decompose_slower_and_say_so():
    flooded = tuple(m in (6, 7, 8, 9, 10, 11, 12) for m in range(1, 13))
    dry = project_soc(climate(), clay_pct=38, initial_soc_t_c_ha=32,
                      baseline=Management("b"), practices=["residue_retention"],
                      start_year=2026, horizon=10, draws=10)
    paddy = project_soc(climate(), clay_pct=38, initial_soc_t_c_ha=32,
                        baseline=Management("b", flooded=flooded),
                        practices=["residue_retention"],
                        start_year=2026, horizon=10, draws=10)
    assert paddy.plant_input_t_c_ha < dry.plant_input_t_c_ha
    assert any("Shirato" in w for w in paddy.warnings)
