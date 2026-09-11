from datetime import date

import pytest

from carbonstack.domain import TrackKind
from carbonstack.feed import (
    CH4_GWP100, FeedProvider, REVISIT_DAYS, series, summarise_seasons,
)
from carbonstack.sites import NYERI, SITES, THANJAVUR, as_project


# --- sites ------------------------------------------------------------------

def test_both_pilot_sites_are_in_the_requested_size_band():
    for site in SITES.values():
        assert 2.0 <= site.area_ha <= 3.0


def test_sites_sit_at_their_stated_coordinates():
    """Boundaries are drawn around a real point, so the centroid must land on
    it. A plot that drifts off its village is a data-entry class of bug that
    is very hard to see in a table."""
    for site in SITES.values():
        from carbonstack.geo import centroid
        lon, lat = centroid(site.boundary)
        assert abs(lat - site.lat) < 0.002
        assert abs(lon - site.lon) < 0.002


def test_sites_convert_to_clean_projects():
    for site in SITES.values():
        project = as_project(site)
        assert project.eligibility_issues() == {}
        assert project.creditable_area_ha() == pytest.approx(site.area_ha)


def test_climatology_has_twelve_months_and_the_right_shape():
    # Thanjavur is north-east monsoon: wettest in Oct-Nov, driest in Feb-Mar.
    rain = THANJAVUR.climate.monthly_rain_mm
    assert len(rain) == 12
    assert rain.index(max(rain)) == 10          # November
    # Nyeri is bimodal: April and November both well above the annual mean.
    krain = NYERI.climate.monthly_rain_mm
    mean = sum(krain) / 12
    assert krain[3] > mean * 1.5                # April, long rains
    assert krain[10] > mean * 1.5               # November, short rains


def test_seasons_wrap_the_new_year():
    """Samba runs August to January. A season test that cannot cross a year
    boundary silently drops half the crop."""
    samba = next(s for s in THANJAVUR.seasons if s.name == "Samba")
    assert samba.contains(date(2026, 9, 1))
    assert samba.contains(date(2027, 1, 10))
    assert not samba.contains(date(2026, 3, 1))
    assert 0.0 < samba.progress(date(2026, 11, 1)) < 1.0


# --- feed -------------------------------------------------------------------

def test_feed_is_deterministic():
    a = series(NYERI, date(2025, 3, 20), date(2026, 3, 20))
    b = series(NYERI, date(2025, 3, 20), date(2026, 3, 20))
    assert [r.to_dict() for r in a] == [r.to_dict() for r in b]


def test_feed_uses_the_real_revisit_cadence():
    rs = series(NYERI, date(2025, 3, 20), date(2025, 6, 20))
    gaps = {(b.day - a.day).days for a, b in zip(rs, rs[1:])}
    assert gaps == {REVISIT_DAYS}


def test_cloud_loss_is_worse_in_the_wet_season():
    """Optical monitoring fails when it rains, which is exactly when crops
    grow. A feed that ignores this makes the pipeline look easier than it is."""
    rs = series(THANJAVUR, date(2025, 1, 1), date(2027, 12, 31))
    wet = [r for r in rs if r.day.month in (10, 11)]
    dry = [r for r in rs if r.day.month in (2, 3)]
    wet_loss = sum(1 for r in wet if r.ndvi is None) / len(wet)
    dry_loss = sum(1 for r in dry if r.ndvi is None) / len(dry)
    assert wet_loss > dry_loss


def test_rice_methane_only_flows_when_the_field_is_flooded_and_cropped():
    rs = series(THANJAVUR, date(2025, 6, 1), date(2026, 12, 31))
    fallow = [r for r in rs if r.season == "fallow"]
    assert fallow
    assert all(r.ch4_baseline_kg_ha_day == 0 for r in fallow)
    cropped = [r for r in rs if r.season not in ("", "fallow")]
    assert any(r.ch4_baseline_kg_ha_day > 0 for r in cropped)


def test_awd_reduces_methane_against_the_baseline():
    rs = series(THANJAVUR, date(2025, 6, 1), date(2026, 3, 1))
    base = sum(r.ch4_baseline_kg_ha_day for r in rs)
    proj = sum(r.ch4_project_kg_ha_day for r in rs)
    assert proj < base
    assert any(r.dry_down for r in rs)


def test_a_lapsed_season_produces_no_dry_downs_and_low_confidence():
    """The case the review workflow exists for: the farmer did not do it."""
    rs = series(THANJAVUR, date(2025, 6, 1), date(2026, 12, 31),
                awd_lapse_season="Kuruvai", awd_lapse_year=2026)
    lapsed = next(s for s in summarise_seasons(rs)
                  if s.year == 2026 and s.season == "Kuruvai")
    good = next(s for s in summarise_seasons(rs)
                if s.year == 2025 and s.season == "Kuruvai")
    assert lapsed.dry_down_events == 0
    assert lapsed.abatement_tco2e_ha == 0.0
    assert lapsed.adoption_confidence < 0.5      # below the crediting floor
    assert good.adoption_confidence > 0.5


def test_abatement_converts_methane_at_gwp100():
    rs = series(THANJAVUR, date(2025, 6, 1), date(2025, 12, 31))
    s = summarise_seasons(rs)[0]
    delta_kg = s.baseline_ch4_kg_ha - s.project_ch4_kg_ha
    assert s.abatement_tco2e_ha == pytest.approx(delta_kg * CH4_GWP100 / 1000.0)


def test_pollarding_is_flagged_rather_than_read_as_deforestation():
    rs = series(NYERI, date(2025, 3, 20), date(2027, 12, 31), stumping_year=2026)
    flagged = [r for r in rs if any("pollarding" in f for f in r.flags)]
    assert flagged
    assert all(r.canopy_height_m is not None for r in flagged)


def test_shade_canopy_grows_at_a_plausible_rate():
    """Grevillea reaches roughly 3 m by year two and 7-8 m by year five.
    An allometry fed an implausible growth curve produces confident nonsense."""
    rs = series(NYERI, NYERI.enrolled_on, date(2035, 12, 31))
    by_year = {}
    for r in rs:
        if r.canopy_height_m is not None:
            by_year[r.day.year] = r.canopy_height_m
    assert 2.0 < by_year[2027] < 4.5
    assert 6.0 < by_year[2030] < 9.5
    assert by_year[2035] < NYERI.shade_peak_height_m


def test_feed_provider_serves_the_standard_interface():
    from carbonstack.remote_sensing import Provider

    rs = series(NYERI, NYERI.enrolled_on, date(2027, 12, 31))
    provider = FeedProvider(rs, season_confidence={2026: 0.8})
    assert isinstance(provider, Provider)

    project = as_project(NYERI)
    plot = next(iter(project.plots.values()))

    height = provider.retrieve(plot, "canopy_height_m", date(2027, 6, 1))
    assert height is not None and height.value > 0
    assert provider.retrieve(plot, "practice_adopted", date(2026, 6, 1)).value == 0.8
    assert provider.retrieve(plot, "practice_adopted", date(2099, 6, 1)) is None


def test_feed_provider_never_returns_a_future_reading():
    """Crediting a vintage on data that had not been captured yet is the
    simplest possible way to fail an audit."""
    rs = series(NYERI, NYERI.enrolled_on, date(2030, 12, 31))
    provider = FeedProvider(rs)
    project = as_project(NYERI)
    plot = next(iter(project.plots.values()))
    cutoff = date(2027, 6, 1)
    assert provider.retrieve(plot, "canopy_height_m", cutoff).observed_on <= cutoff


def test_quantifying_a_site_end_to_end_yields_credits():
    from carbonstack import methodology
    from carbonstack.methodology.vm0047 import PerformanceBenchmark

    project = as_project(NYERI)
    rs = series(NYERI, NYERI.enrolled_on, date(2033, 12, 31), stumping_year=2026)
    m = methodology.get("VM0047",
                        benchmark=PerformanceBenchmark(t_co2e_per_ha_yr=0.6))
    result = m.quantify(project, FeedProvider(rs), 2031)
    assert result.net_t > 0
    assert result.area_ha == pytest.approx(NYERI.area_ha)
    assert result.relative_uncertainty > 0


# --- the roll-up bug this test exists to prevent -----------------------------

def _fake_season(season, year, baseline, abatement, confidence):
    from carbonstack.feed import SeasonSummary
    return SeasonSummary(
        year=year, season=season, start=date(year, 6, 1), end=date(year, 9, 1),
        revisits=20, clear_revisits=15, dry_down_events=0 if abatement == 0 else 3,
        baseline_ch4_kg_ha=baseline,
        project_ch4_kg_ha=baseline - abatement * 1000 / CH4_GWP100,
        adoption_confidence=confidence,
    )


def test_year_confidence_does_not_let_a_lapsed_season_vanish():
    """The tempting weight is achieved abatement. It is wrong: a lapsed season
    abates nothing, so it carries zero weight and disappears from the average,
    and a year with one good season and one lapse scores like a clean year.
    Weighting by baseline exposure keeps the lapse in view."""
    from carbonstack.feed import year_confidence

    good = _fake_season("Kuruvai", 2026, baseline=90.0, abatement=0.5, confidence=0.9)
    lapsed = _fake_season("Samba", 2026, baseline=85.0, abatement=0.0, confidence=0.2)

    honest = year_confidence([good, lapsed])

    weight = good.abatement_tco2e_ha + lapsed.abatement_tco2e_ha
    abatement_weighted = (
        (good.adoption_confidence * good.abatement_tco2e_ha
         + lapsed.adoption_confidence * lapsed.abatement_tco2e_ha) / weight
    )
    assert abatement_weighted == pytest.approx(0.9)   # the lapse vanished
    assert honest < 0.6                                # it does not, here
    assert lapsed.adoption_confidence < honest < good.adoption_confidence


def test_year_confidence_of_a_clean_year_is_high():
    from carbonstack.feed import year_confidence
    a = _fake_season("Kuruvai", 2025, 90.0, 0.5, 0.88)
    b = _fake_season("Samba", 2025, 85.0, 0.6, 0.91)
    assert 0.88 <= year_confidence([a, b]) <= 0.91


def test_year_confidence_handles_no_seasons():
    from carbonstack.feed import year_confidence
    assert year_confidence([]) == 0.0


def test_retrieval_window_prefers_the_clearest_pass():
    """Trusting whichever pass lands on the reporting date hands quantification
    its worst measurement whenever that one was cloudy, and the uncertainty
    deduction then swings between vintages for no physical reason."""
    from carbonstack.feed import FeedProvider

    rs = series(NYERI, NYERI.enrolled_on, date(2032, 12, 31), stumping_year=2026)
    provider = FeedProvider(rs)
    project = as_project(NYERI)
    plot = next(iter(project.plots.values()))

    sigmas = []
    for year in range(2027, 2032):
        hit = provider.retrieve(plot, "canopy_height_m", date(year, 12, 31))
        sigmas.append(hit.uncertainty / hit.value)

    spread = max(sigmas) - min(sigmas)
    assert spread < 0.18, f"relative uncertainty swings too much between vintages: {sigmas}"


def test_flags_near_surfaces_management_events_for_review():
    from carbonstack.feed import FeedProvider

    rs = series(NYERI, NYERI.enrolled_on, date(2028, 12, 31), stumping_year=2026)
    provider = FeedProvider(rs)
    assert any("pollarding" in f for f in provider.flags_near(date(2026, 12, 31)))
    assert not any("pollarding" in f for f in provider.flags_near(date(2028, 12, 31)))
