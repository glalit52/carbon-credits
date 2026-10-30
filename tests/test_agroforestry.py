"""Species allometry, survival, and the census-based VM0047 approach.

The area-based path reads a stocking index over a contiguous canopy. Trees on
a paddy bund are a line of stems narrower than a Sentinel-2 pixel, so an index
returns near zero over a thriving planting -- not a conservative estimate, a
wrong one. These tests pin the census instrument that replaces it.
"""

import json
from datetime import date

import pytest

from carbonstack import methodology
from carbonstack.agroforestry import (
    CARBON_FRACTION, CO2_PER_C, BenchmarkProvider, CensusInventory, SPECIES,
    Species, StemMeasurement, SurvivalSurvey,
)
from carbonstack.sites import NYERI, as_project


def survey(alive=79, sampled=90, planted=1200, surveyor="field team A"):
    return SurvivalSurvey("P1", date(2030, 6, 1), stems_planted=planted,
                          stems_sampled=sampled, stems_alive=alive,
                          surveyor=surveyor)


def inventory(dbh=16.0, height=8.0, n=12, **kw):
    return CensusInventory(
        "P1", date(2030, 6, 1), survival=survey(**kw),
        sample=[StemMeasurement("grevillea_robusta", dbh_cm=dbh + i * 0.6,
                                height_m=height + i * 0.25) for i in range(n)])


# --- allometry --------------------------------------------------------------

def test_chave_2014_matches_the_published_form():
    """AGB = 0.0673 * (rho * D^2 * H)^0.976. A verifier will recognise it, so
    it must be exactly that and not an approximation of it."""
    s = Species(name="x", equation="chave2014", wood_density_g_cm3=0.58)
    expected = 0.0673 * (0.58 * 18 ** 2 * 9) ** 0.976
    assert s.agb_kg(dbh_cm=18, height_m=9) == pytest.approx(expected)


def test_carbon_conversion_includes_roots():
    s = Species(name="x", equation="chave2014", wood_density_g_cm3=0.58,
                root_shoot=0.27)
    agb = s.agb_kg(dbh_cm=18, height_m=9)
    assert s.co2e_kg(dbh_cm=18, height_m=9) == pytest.approx(
        agb * 1.27 * CARBON_FRACTION * CO2_PER_C)


def test_a_power_law_needs_its_exponent():
    with pytest.raises(ValueError, match="positive exponent"):
        Species(name="x", equation="power_dbh", a=1.0, b=0.0)


def test_an_unknown_allometric_form_is_refused():
    with pytest.raises(ValueError, match="unknown allometric form"):
        Species(name="x", equation="magic")


def test_chave_needs_both_measurements():
    s = SPECIES["melia_dubia"]
    with pytest.raises(ValueError, match="both diameter and height"):
        s.agb_kg(dbh_cm=18)


def test_height_only_allometry_works_for_remote_sensed_stems():
    s = Species(name="x", equation="power_height", a=2.0, b=1.8)
    assert s.agb_kg(height_m=10) == pytest.approx(2.0 * 10 ** 1.8)


def test_a_generic_equation_knows_it_is_generic():
    """The tree project's Tier 3 distinction: a local fit is worth credits,
    and the code has to be able to tell the difference."""
    assert not SPECIES["grevillea_robusta"].is_locally_calibrated
    local = Species(name="Grevillea robusta", equation="power_dbh", a=0.11,
                    b=2.42, source="Kenyan highland fit, Kuyah et al.")
    assert local.is_locally_calibrated


def test_a_stem_with_no_size_has_no_biomass():
    assert SPECIES["melia_dubia"].agb_kg(dbh_cm=0, height_m=0) == 0.0


# --- survival ---------------------------------------------------------------

def test_the_lower_bound_is_credited_not_the_point_estimate():
    """Crediting the point estimate claims trees the surveyor did not find."""
    s = survey(alive=79, sampled=90)
    assert s.survival_rate == pytest.approx(79 / 90)
    assert s.survival_lower_bound() < s.survival_rate
    assert s.surviving_stems < s.stems_planted * s.survival_rate


def test_a_full_census_has_no_sampling_error():
    """The finite population correction: uncertainty that was not incurred
    should not be charged for."""
    s = survey(alive=1000, sampled=1200, planted=1200)
    assert s.standard_error == 0.0
    assert s.survival_lower_bound() == pytest.approx(s.survival_rate)


def test_a_bigger_sample_narrows_the_interval():
    small = survey(alive=17, sampled=20)
    large = survey(alive=850, sampled=1000, planted=1200)
    assert large.standard_error < small.standard_error


def test_impossible_surveys_are_refused():
    with pytest.raises(ValueError, match="no sampled stems"):
        survey(sampled=0)
    with pytest.raises(ValueError, match="alive out of"):
        SurvivalSurvey("P1", date(2030, 6, 1), stems_planted=100,
                       stems_sampled=10, stems_alive=11)
    with pytest.raises(ValueError, match="more stems than were planted"):
        SurvivalSurvey("P1", date(2030, 6, 1), stems_planted=10,
                       stems_sampled=20, stems_alive=5)


def test_a_thin_sample_is_flagged():
    s = survey(alive=9, sampled=10, planted=1200)
    assert any("below 5%" in p for p in s.issues())


def test_a_failing_planting_needs_replacing_not_crediting():
    s = survey(alive=50, sampled=90)
    assert s.needs_replanting
    assert any("needs replacing" in p for p in s.issues())


def test_an_unattributed_survey_is_flagged():
    assert any("no surveyor" in p for p in survey(surveyor=" ").issues())


# --- census inventory -------------------------------------------------------

def test_stock_is_surviving_stems_times_the_mean_stem():
    inv = inventory()
    total, _ = inv.stock()
    expected = inv.survival.surviving_stems * inv.mean_co2e_per_stem_kg / 1000.0
    assert total == pytest.approx(expected)


def test_uncertainty_combines_sampling_allometry_and_survival():
    total, relative = inventory().stock()
    assert 0 < relative < 1
    # Every source is present, so the combination exceeds any one of them.
    inv = inventory()
    assert relative > inv.stem_sampling_error
    assert relative > inv.allometry_error * 0.9


def test_a_single_measured_stem_cannot_characterise_the_spread():
    inv = inventory(n=1)
    assert inv.stem_sampling_error == 1.0


def test_an_inventory_with_no_allometry_for_its_species_is_refused():
    with pytest.raises(ValueError, match="no allometry for species"):
        CensusInventory("P1", date(2030, 6, 1), survival=survey(),
                        sample=[StemMeasurement("unobtainium", dbh_cm=10,
                                                height_m=5)])


def test_the_derivation_names_the_conservative_choice():
    calc = None
    from carbonstack.audit import Calculation
    calc = Calculation("x", "tCO2e")
    inventory().stock(calc=calc)
    labels = [t.label for t in calc]
    assert "survival, lower 90% bound" in labels
    assert "surviving stems credited" in labels
    assert any("VM0047" in c for c in calc.citations)
    assert any("Chave" in c for c in calc.citations)


# --- the benchmark provider -------------------------------------------------

def test_the_placeholder_benchmark_is_not_vetted():
    """A benchmark quietly set near zero turns every project into a high
    performer, which is the failure VM0047 exists to close."""
    provider = BenchmarkProvider()
    assert not provider.is_vetted
    point = provider.benchmark_for(project_id="P", year=2030)
    assert "Verra-vetted" in point.provider
    assert point.control_units == 0


# --- the census methodology -------------------------------------------------

@pytest.fixture
def project():
    return as_project(NYERI)


def run(project, plot_id, *, now=None, prior=None, **kw):
    now = now or inventory()
    inv = CensusInventory(plot_id, now.measured_on, survival=SurvivalSurvey(
        plot_id, now.survival.surveyed_on, now.survival.stems_planted,
        now.survival.stems_sampled, now.survival.stems_alive,
        now.survival.surveyor), sample=now.sample)
    priors = {}
    if prior is not None:
        priors[plot_id] = CensusInventory(
            plot_id, prior.measured_on, survival=SurvivalSurvey(
                plot_id, prior.survival.surveyed_on, prior.survival.stems_planted,
                prior.survival.stems_sampled, prior.survival.stems_alive,
                prior.survival.surveyor), sample=prior.sample)
    return methodology.census_pathway(**kw).quantify(
        project, inventories={plot_id: inv}, prior_inventories=priors,
        reporting_year=2030)


def test_census_credits_growth_over_the_prior_inventory(project):
    plot_id = next(iter(project.plots))
    result = run(project, plot_id, now=inventory(dbh=16, height=8),
                 prior=inventory(dbh=14, height=7))
    assert result.gross_t > 0
    assert result.net_t > 0
    assert result.net_t < result.gross_t


def test_a_failing_planting_is_excluded_and_flagged(project):
    plot_id = next(iter(project.plots))
    result = run(project, plot_id, now=inventory(alive=55))
    assert result.gross_t == 0.0
    assert any("flagged for replanting" in w for w in result.warnings)


def test_an_unvetted_benchmark_blocks_issuance_with_a_warning(project):
    plot_id = next(iter(project.plots))
    result = run(project, plot_id)
    assert any("not a Verra-vetted data service provider" in w
               for w in result.warnings)


def test_plots_without_a_census_contribute_nothing(project):
    plot_id = next(iter(project.plots))
    result = methodology.census_pathway().quantify(
        project, inventories={}, reporting_year=2030)
    assert result.gross_t == 0.0
    assert any("no census inventory" in w for w in result.warnings)


def test_growth_below_the_benchmark_questions_additionality(project):
    plot_id = next(iter(project.plots))
    result = run(project, plot_id, now=inventory(dbh=16, height=8),
                 prior=inventory(dbh=16, height=8),
                 benchmark=BenchmarkProvider(t_co2e_per_ha_yr=50.0))
    assert result.gross_t == 0.0
    assert any("additionality is in question" in w for w in result.warnings)


def test_the_census_result_names_the_approach(project):
    plot_id = next(iter(project.plots))
    result = run(project, plot_id)
    assert "census-based" in result.methodology
    summary = result.calculations[-1]
    assert any("census-based approach" in c for c in summary.citations)


# --- persistence, CLI and API ----------------------------------------------

import csv as _csv

from carbonstack import evidence
from carbonstack.api import dispatch
from carbonstack.cli import main
from carbonstack.sites import NYERI, as_project
from carbonstack.store import Store
from carbonstack.store.repo import StoreError


@pytest.fixture
def coffee():
    with Store(":memory:", actor="tester") as s:
        s.save_project(as_project(NYERI), methodology_id="VM0047")
        yield s


def stored_inventory(plot_id, *, measured_on=date(2027, 11, 20), alive=35,
                     dbh=14.9, height=7.4, surveyor="J. Wanjiku", stems=40):
    return CensusInventory(
        plot_id=plot_id, measured_on=measured_on,
        survival=SurvivalSurvey(
            plot_id=plot_id, surveyed_on=measured_on, stems_planted=340,
            stems_sampled=40, stems_alive=alive, surveyor=surveyor),
        sample=[StemMeasurement("grevillea_robusta", dbh_cm=dbh + i * 0.1,
                                height_m=height) for i in range(stems)])


def test_an_inventory_survives_a_round_trip(coffee):
    plot_id = next(iter(coffee.load_project(NYERI.id).plots))
    coffee.add_tree_inventory(NYERI.id, stored_inventory(plot_id),
                              actor="tester")

    back = coffee.tree_inventories(NYERI.id)
    assert set(back) == {plot_id}
    assert back[plot_id].stock()[0] == pytest.approx(
        stored_inventory(plot_id).stock()[0])
    assert back[plot_id].survival.surveyor == "J. Wanjiku"


def test_the_allometry_is_stored_with_the_measurements(coffee):
    """A local fit that lands next year must not silently restate this year's
    inventory at a new number."""
    plot_id = next(iter(coffee.load_project(NYERI.id).plots))
    coffee.add_tree_inventory(NYERI.id, stored_inventory(plot_id),
                              actor="tester")
    species = coffee.tree_inventories(NYERI.id)[plot_id].species
    assert species["grevillea_robusta"].wood_density_g_cm3 == pytest.approx(0.58)
    assert not species["grevillea_robusta"].is_locally_calibrated


def test_a_survey_with_no_surveyor_is_refused(coffee):
    plot_id = next(iter(coffee.load_project(NYERI.id).plots))
    with pytest.raises(StoreError, match="no surveyor"):
        coffee.add_tree_inventory(
            NYERI.id, stored_inventory(plot_id, surveyor=" "), actor="tester")


def test_reingesting_the_same_visit_is_a_no_op(coffee):
    plot_id = next(iter(coffee.load_project(NYERI.id).plots))
    coffee.add_tree_inventory(NYERI.id, stored_inventory(plot_id), actor="t")
    coffee.add_tree_inventory(NYERI.id, stored_inventory(plot_id), actor="t")
    assert len(coffee.tree_inventories(NYERI.id)) == 1


def test_a_year_filter_reads_the_inventory_as_it_stood(coffee):
    """A plot measured every second year keeps its stock in between rather
    than appearing to vanish."""
    plot_id = next(iter(coffee.load_project(NYERI.id).plots))
    coffee.add_tree_inventory(
        NYERI.id, stored_inventory(plot_id, measured_on=date(2026, 11, 15),
                                   dbh=12.4, height=6.2), actor="t")
    coffee.add_tree_inventory(
        NYERI.id, stored_inventory(plot_id, measured_on=date(2028, 11, 20)),
        actor="t")

    assert coffee.tree_inventories(NYERI.id, year=2025) == {}
    older = coffee.tree_inventories(NYERI.id, year=2027)[plot_id]
    newer = coffee.tree_inventories(NYERI.id, year=2028)[plot_id]
    assert older.measured_on == date(2026, 11, 15)
    assert newer.stock()[0] > older.stock()[0]


def test_storing_an_inventory_lands_in_the_event_chain(coffee):
    plot_id = next(iter(coffee.load_project(NYERI.id).plots))
    coffee.add_tree_inventory(NYERI.id, stored_inventory(plot_id), actor="jane")
    event = [e for e in coffee.events()
             if e["kind"] == "trees.inventory_stored"][-1]
    assert event["actor"] == "jane"
    assert event["payload"]["surveyor"] == "J. Wanjiku"
    assert event["payload"]["local_allometry"] is False
    assert coffee.verify_chain()[0]


def _field_csv(path, plot_id, *, alive=35, measured_on="2027-11-20"):
    rows = [{
        "plot_id": plot_id, "measured_on": measured_on,
        "surveyed_on": measured_on, "surveyor": "J. Wanjiku",
        "stems_planted": 340, "stems_sampled": 40, "stems_alive": alive,
        "species_key": "grevillea_robusta",
        "dbh_cm": round(14.0 + i * 0.1, 1), "height_m": 7.4,
    } for i in range(40)]
    with open(path, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return str(path)


def test_cli_ingests_a_field_census_and_quantifies(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    assert main(["--db", db, "enroll", "gatugi"]) == 0
    csv_path = _field_csv(tmp_path / "field.csv", "KE-NYR-01-P1")

    assert main(["--db", db, "trees", "ingest", "KE-NYR-01", csv_path,
                 "--actor", "lalit"]) == 0
    assert main(["--db", db, "trees", "survival", "KE-NYR-01"]) == 0
    assert main(["--db", db, "trees", "quantify", "KE-NYR-01",
                 "--year", "2027", "--actor", "lalit"]) == 0
    out = capsys.readouterr().out
    assert "census-based" in out
    assert "not a Verra-vetted data service provider" in out


def test_cli_quantify_refuses_without_a_census(tmp_path):
    db = str(tmp_path / "t.db")
    main(["--db", db, "enroll", "gatugi"])
    with pytest.raises(SystemExit, match="credits what was counted"):
        main(["--db", db, "trees", "quantify", "KE-NYR-01", "--year", "2027",
              "--actor", "lalit"])


def test_cli_species_flags_every_generic_equation(capsys):
    assert main(["trees", "species"]) == 0
    out = capsys.readouterr().out
    listed = [l for l in out.splitlines() if "chave2014" in l]
    assert len(listed) == len(SPECIES)
    assert all(l.rstrip().endswith("GENERIC") for l in listed)
    assert f"{len(SPECIES)} of {len(SPECIES)} species carry a generic" in out


def test_api_reports_the_census_and_the_unvetted_benchmark(coffee):
    plot_id = next(iter(coffee.load_project(NYERI.id).plots))
    coffee.add_tree_inventory(NYERI.id, stored_inventory(plot_id), actor="t")

    status, body = dispatch(coffee, "GET", f"/api/projects/{NYERI.id}/trees",
                            {}, None)
    assert status == 200
    assert body["stems_planted"] == 340
    assert body["stems_credited"] < 340        # the lower bound, not the count
    assert body["benchmark_vetted"] is False
    assert body["plots"][0]["locally_calibrated"] is False

    status, older = dispatch(coffee, "GET",
                             f"/api/projects/{NYERI.id}/trees",
                             {"year": ["2020"]}, None)
    assert older["plots"] == []


def test_api_publishes_the_allometry_catalogue(coffee):
    status, body = dispatch(coffee, "GET", "/api/allometry", {}, None)
    assert status == 200
    assert {s["key"] for s in body["species"]} >= {"grevillea_robusta"}
    assert all(s["locally_calibrated"] is False for s in body["species"])


def test_the_evidence_pack_carries_the_census(coffee, tmp_path):
    plot_id = next(iter(coffee.load_project(NYERI.id).plots))
    coffee.add_tree_inventory(NYERI.id, stored_inventory(plot_id), actor="t")
    out = evidence.build(coffee, NYERI.id, tmp_path / "pack")

    rows = list(_csv.DictReader((out / "tree_inventory.csv").open()))
    assert rows[0]["surveyor"] == "J. Wanjiku"
    assert rows[0]["allometry"] == "generic"

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["trees"]["stems_planted"] == 340
    assert manifest["trees"]["plots_on_generic_allometry"] == 1
