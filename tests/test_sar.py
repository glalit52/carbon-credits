"""Sentinel-1 water-regime detection.

The rice claim is that the field was dry. These tests pin the detector that
now answers that question, and -- more importantly -- pin what it refuses to
answer. The detector sees backscatter and nothing else; `sar_truth` exists
only so the tests can score it.
"""

import json
from datetime import date

import pytest

from carbonstack import methodology, sar
from carbonstack.api import dispatch
from carbonstack.cli import main
from carbonstack.feed import (
    FeedProvider, sar_seasons, sar_series, sar_truth, series,
    summarise_seasons, year_confidence,
)
from carbonstack.sar import (
    CROSSOVER_STAGE, Classification, SarPass, SarProvider, WaterRegimeDetector,
    WaterState, score, summarise_regime,
)
from carbonstack.sites import THANJAVUR, as_project
from carbonstack.store import Store

LAPSE = {"awd_lapse_season": "Kuruvai", "awd_lapse_year": 2026}
END = date(2027, 12, 31)


def passes():
    return sar_series(THANJAVUR, THANJAVUR.enrolled_on, END, **LAPSE)


def truth():
    return sar_truth(THANJAVUR, THANJAVUR.enrolled_on, END, **LAPSE)


# --- the physics ------------------------------------------------------------

def test_a_bare_flooded_field_is_darker_than_a_bare_drained_one():
    """The mirror. This is the signal everybody knows about."""
    assert sar.flooded_vv_db(0.0) < sar.drained_vv_db(0.0) - 5


def test_a_flooded_field_under_canopy_is_brighter_than_a_drained_one():
    """Double bounce off stems standing in water. This is the one that breaks
    fixed-threshold flood maps, and it is why the detector is stage-aware."""
    assert sar.flooded_vv_db(1.0) > sar.drained_vv_db(1.0) + 2


def test_the_two_responses_cross_mid_season():
    assert 0.3 < CROSSOVER_STAGE < 0.8
    assert sar.flooded_vv_db(CROSSOVER_STAGE) == pytest.approx(
        sar.drained_vv_db(CROSSOVER_STAGE), abs=1e-9)


def test_incidence_angle_is_normalised_before_anything_is_compared():
    """Two passes of the same field from different tracks must not differ
    just because of geometry."""
    near = sar.simulate_pass("p", date(2026, 7, 1), water_frac=0.9, stage=0.8,
                             incidence_deg=33.0)
    far = sar.simulate_pass("p", date(2026, 7, 1), water_frac=0.9, stage=0.8,
                            incidence_deg=44.0)
    assert near.vv_db != far.vv_db
    assert near.vv_normalised_db == pytest.approx(far.vv_normalised_db)


# --- the refusal ------------------------------------------------------------

def test_the_detector_abstains_where_the_two_states_are_inseparable():
    """At the crossover there is no information in VV. A call there would be
    a coin flip dressed up as a measurement."""
    p = sar.simulate_pass("p", date(2026, 8, 1), water_frac=0.9,
                          stage=CROSSOVER_STAGE)
    call = WaterRegimeDetector().classify_one(p)
    assert call.state is WaterState.AMBIGUOUS
    assert call.confidence == 0.0
    assert "not separable" in call.note or "within" in call.note


def test_a_confident_call_is_made_where_the_states_are_far_apart():
    flooded = WaterRegimeDetector().classify_one(
        sar.simulate_pass("p", date(2026, 6, 20), water_frac=0.95, stage=0.05))
    drained = WaterRegimeDetector().classify_one(
        sar.simulate_pass("p", date(2026, 6, 20), water_frac=0.05, stage=0.05))
    assert flooded.state is WaterState.FLOODED
    assert drained.state is WaterState.DRAINED
    assert flooded.confidence > 0.8 and drained.confidence > 0.8


def test_an_unreadable_pass_between_two_agreeing_ones_is_carried_across():
    det = WaterRegimeDetector()
    days = [date(2026, 7, 1), date(2026, 7, 7), date(2026, 7, 13)]
    calls = [
        Classification(days[0], WaterState.FLOODED, 0.95, 0.2, 4.0, -17.0),
        Classification(days[1], WaterState.AMBIGUOUS, 0.5, 0.54, 0.1, -17.4),
        Classification(days[2], WaterState.FLOODED, 0.93, 0.2, 4.0, -17.2),
    ]
    det.infer_across_gaps(calls)
    assert calls[1].state is WaterState.FLOODED
    assert calls[1].inferred
    assert calls[1].confidence < calls[0].confidence   # weaker evidence


def test_a_gap_between_disagreeing_passes_is_never_filled():
    """The transition is exactly what must not be invented: an AWD event
    conjured out of an unreadable pass is the failure mode."""
    det = WaterRegimeDetector()
    calls = [
        Classification(date(2026, 7, 1), WaterState.FLOODED, 0.95, 0.2, 4.0, -17.0),
        Classification(date(2026, 7, 7), WaterState.AMBIGUOUS, 0.5, 0.54, 0.1, -14.0),
        Classification(date(2026, 7, 13), WaterState.DRAINED, 0.05, 0.2, 4.0, -12.0),
    ]
    det.infer_across_gaps(calls)
    assert calls[1].state is WaterState.AMBIGUOUS
    assert not calls[1].inferred


def test_a_large_backscatter_step_blocks_the_inference():
    det = WaterRegimeDetector()
    calls = [
        Classification(date(2026, 7, 1), WaterState.FLOODED, 0.95, 0.2, 4.0, -17.0),
        Classification(date(2026, 7, 7), WaterState.AMBIGUOUS, 0.5, 0.54, 0.1, -11.0),
        Classification(date(2026, 7, 13), WaterState.FLOODED, 0.93, 0.2, 4.0, -17.2),
    ]
    det.infer_across_gaps(calls)
    assert calls[1].state is WaterState.AMBIGUOUS


# --- what a season is worth -------------------------------------------------

def _regime(year, season):
    det = WaterRegimeDetector()
    grouped = sar_seasons(THANJAVUR, passes())
    return summarise_regime(det.classify(grouped[(year, season)]),
                            season=season, year=year)


def test_the_harvest_drain_is_detected_and_excluded():
    """Every paddy is drained before harvest, in the baseline too. Counting
    it would credit the counterfactual."""
    regime = _regime(2026, "Kuruvai")
    assert any(s.terminal for s in regime.spells)
    assert all(not s.terminal for s in regime.qualifying_spells)
    assert any("drained for harvest too" in w for w in regime.warnings)


def test_a_season_with_no_awd_is_detected_as_such():
    """2026 Kuruvai is the injected lapse: the farmer did not practise AWD.
    Nothing tells the detector that."""
    regime = _regime(2026, "Kuruvai")
    assert regime.qualifying_spells == []
    assert regime.adoption_confidence < 0.35
    assert any("continuously flooded" in w for w in regime.warnings)


def test_a_season_that_did_practise_awd_scores_well_above_it():
    practised = _regime(2025, "Kuruvai")
    lapsed = _regime(2026, "Kuruvai")
    assert len(practised.qualifying_spells) >= 2
    assert practised.adoption_confidence > lapsed.adoption_confidence + 0.3


def test_a_single_pass_spell_needs_a_clean_call_to_count():
    det = WaterRegimeDetector()
    day = date(2026, 7, 1)
    marginal = [Classification(day, WaterState.DRAINED, 0.28, 0.2, 4.0, -12.0)]
    clean = [Classification(day, WaterState.DRAINED, 0.02, 0.2, 4.0, -12.0)]
    weak = summarise_regime(marginal, season="Kuruvai", year=2026,
                            min_confidence=0.4)
    strong = summarise_regime(clean, season="Kuruvai", year=2026)
    assert weak.qualifying_spells == []
    assert len(strong.qualifying_spells) == 1


def test_a_year_is_weighted_by_baseline_exposure_not_by_performance():
    """A lapsed season abates nothing, so weighting by abatement would give
    it no weight and it would vanish from the year."""
    provider = SarProvider.from_passes(sar_seasons(THANJAVUR, passes()))
    year = provider.regime(2026)
    seasons = {s.season: s.adoption_confidence for s in year.seasons}
    worst, best = min(seasons.values()), max(seasons.values())
    assert worst < year.adoption_confidence < best
    assert any("needs review" in w for w in year.warnings)


# --- how well it works ------------------------------------------------------

def test_the_detector_recovers_the_hidden_water_state():
    result = score(WaterRegimeDetector().classify(passes()), truth())
    assert result["called"] > 60
    assert result["accuracy"] > 0.90
    # Calling a flooded field dry is the error that over-credits, so it is
    # the one with a budget.
    assert result["false_negative"] <= 5
    assert result["precision_flooded"] > 0.90


def test_abstaining_is_not_scored_as_an_error():
    result = score(WaterRegimeDetector().classify(passes()), truth())
    assert result["abstained"] > 0
    assert result["called"] + result["abstained"] == len(truth())


def test_radar_sees_more_of_the_season_than_optical_does():
    """The reason this is SAR at all: AWD is practised in the monsoon."""
    optical = summarise_seasons(
        series(THANJAVUR, THANJAVUR.enrolled_on, END, **LAPSE))
    clear = sum(s.clear_revisits for s in optical)
    revisits = sum(s.revisits for s in optical)
    provider = SarProvider.from_passes(sar_seasons(THANJAVUR, passes()))
    radar = [provider.regime(y) for y in (2025, 2026)]
    assert clear / revisits < min(r.coverage for r in radar)


def test_detection_is_more_conservative_than_the_asserted_confidence():
    """Measuring costs credits against being told. That is the trade, and it
    should be visible rather than argued."""
    optical = summarise_seasons(
        series(THANJAVUR, THANJAVUR.enrolled_on, END, **LAPSE))
    by_year: dict[int, list] = {}
    for s in optical:
        by_year.setdefault(s.year, []).append(s)
    provider = SarProvider.from_passes(sar_seasons(THANJAVUR, passes()))
    for year in (2025, 2027):
        assert (provider.regime(year).adoption_confidence
                < year_confidence(by_year[year]))


# --- wiring -----------------------------------------------------------------

def test_the_provider_serves_adoption_through_the_standard_interface():
    provider = SarProvider.from_passes(sar_seasons(THANJAVUR, passes()))
    project = as_project(THANJAVUR)
    plot = next(iter(project.plots.values()))
    det = provider.retrieve(plot, "practice_adopted", date(2025, 12, 31))
    assert det is not None
    assert det.source == "sentinel1"
    assert 0 < det.value < 1
    assert provider.retrieve(plot, "canopy_height_m", date(2025, 12, 31)) is None


def test_the_feed_forwards_the_detectors_findings_to_the_vintage():
    """A reviewer signing off a confidence needs the passes behind it, and a
    season that scored badly alone must not be averaged into silence."""
    readings = series(THANJAVUR, THANJAVUR.enrolled_on, END, **LAPSE)
    detector = SarProvider.from_passes(sar_seasons(THANJAVUR, passes()))
    provider = FeedProvider(readings, sar_passes=passes(), adoption=detector)

    project = as_project(THANJAVUR)
    from carbonstack.methodology.vm0051 import CommonPractice, RiceEmissionFactor
    m = methodology.get(
        "VM0051",
        factors={"awd": RiceEmissionFactor(baseline_ch4_kg_ha_season=90.0,
                                           project_ch4_kg_ha_season=70.0)},
        common_practice=CommonPractice(jurisdiction="Tamil Nadu",
                                       awd_penetration=0.04))
    result = m.quantify(project, provider, 2026)

    assert any("detected water regime" in c.name for c in result.calculations)
    assert any("needs review" in w for w in result.warnings)


def test_the_feed_serves_backscatter_as_observations():
    readings = series(THANJAVUR, THANJAVUR.enrolled_on, END, **LAPSE)
    provider = FeedProvider(readings, sar_passes=passes())
    plot = next(iter(as_project(THANJAVUR).plots.values()))
    vv = provider.retrieve(plot, "vv_db", date(2026, 7, 20))
    assert vv is not None
    assert vv.unit == "dB" and vv.source == "sentinel1"
    assert -25 < vv.value < 0


def test_the_evidence_pack_rebuilds_the_calls_from_the_database(tmp_path):
    """If the stored observations cannot reproduce the call, the call is not
    evidence."""
    from carbonstack import evidence, pipeline

    with Store(":memory:", actor="tester") as store:
        store.save_project(as_project(THANJAVUR), methodology_id="VM0051")
        readings = series(THANJAVUR, THANJAVUR.enrolled_on, END, **LAPSE)
        provider = FeedProvider(readings, sar_passes=passes())
        pipeline.monitor(store, THANJAVUR.id, provider,
                         start=date(2025, 6, 1), end=date(2025, 12, 31))
        out = evidence.build(store, THANJAVUR.id, tmp_path / "pack")

    import csv as _csv
    rows = list(_csv.DictReader((out / "water_regime.csv").open()))
    assert rows
    assert {r["state"] for r in rows} <= {"flooded", "drained", "ambiguous"}
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["water_regime"]["passes_classified"] == len(rows)


def test_cli_reports_the_regime_the_passes_and_the_validation(capsys):
    assert main(["rice", "regime", "vallam", "--to", "2027-12-31"]) == 0
    assert main(["rice", "passes", "vallam", "--year", "2026",
                 "--season", "Kuruvai", "--to", "2027-12-31"]) == 0
    assert main(["rice", "validate", "vallam", "--to", "2027-12-31"]) == 0
    out = capsys.readouterr().out
    assert "harvest drain" in out
    assert "continuously flooded" in out
    assert "simulated water regime" in out


def test_cli_refuses_a_non_rice_site():
    with pytest.raises(SystemExit, match="not a rice site"):
        main(["rice", "regime", "gatugi"])
