from datetime import date

import pytest

from carbonstack import methodology
from carbonstack.biomass import Allometry, co2e_per_ha
from carbonstack.domain import (
    Enrollment, Farmer, Plot, Project, TenureBasis, TrackKind,
)
from carbonstack.methodology.base import (
    Deduction, apply_deductions, combine_uncertainty, uncertainty_deduction,
)
from carbonstack.methodology.vm0047 import PerformanceBenchmark
from carbonstack.methodology.vm0042 import EmissionFactor
from carbonstack.remote_sensing import Retrieval, SyntheticProvider


# --- shared deduction rules -------------------------------------------------

def test_deductions_apply_sequentially_not_additively():
    """15% then 20% withholds 32%, not 35%. Summing them instead of compounding
    is a spreadsheet error that shows up as a shortfall at delivery."""
    net, applied = apply_deductions(1000.0, [
        Deduction("uncertainty", 0.15, ""),
        Deduction("buffer", 0.20, ""),
    ])
    assert net == pytest.approx(680.0)
    assert [round(a, 4) for _, a in applied] == [150.0, 170.0]


def test_no_uncertainty_deduction_below_the_allowance():
    assert uncertainty_deduction(0.10).fraction == 0.0
    assert uncertainty_deduction(0.15).fraction == 0.0


def test_uncertainty_deduction_takes_only_the_excess():
    assert uncertainty_deduction(0.40).fraction == pytest.approx(0.25)


def test_combined_uncertainty_sits_between_independent_and_correlated():
    sigmas = [10.0] * 9
    rel = combine_uncertainty(sigmas, 300.0)
    independent = (sum(s ** 2 for s in sigmas) ** 0.5) / 300.0
    correlated = sum(sigmas) / 300.0
    assert independent < rel < correlated


def test_combined_uncertainty_of_nothing_is_zero():
    assert combine_uncertainty([], 0.0) == 0.0
    assert combine_uncertainty([1.0], 0.0) == 0.0


def test_registry_resolves_and_rejects():
    assert set(methodology.available()) == {"VM0047", "VM0042"}
    assert methodology.get("vm0047").id == "VM0047"
    with pytest.raises(KeyError):
        methodology.get("VM9999")


# --- fixtures ---------------------------------------------------------------

def square(lon, lat, side=0.003):
    return [(lon, lat), (lon + side, lat), (lon + side, lat + side), (lon, lat + side)]


def build(n=4, practice="block_planting", track=TrackKind.AGROFORESTRY,
          tenure=TenureBasis.OWNED_TITLE):
    p = Project(id="T1", name="t", track=track, country="IN",
                start_date=date(2025, 7, 1))
    for i in range(n):
        f = p.add_farmer(Farmer(id=f"F{i}", name="A", village="V", district="D",
                                state="S", consent_on=date(2025, 6, 1),
                                consent_reference=f"C/{i}"))
        plot = p.add_plot(Plot(id=f"P{i}", farmer_id=f.id,
                               boundary=square(80 + i * 0.01, 16.3),
                               tenure=tenure, tenure_reference="RoR/1"))
        p.enroll(Enrollment(plot_id=plot.id, project_id=p.id,
                            enrolled_on=date(2025, 7, 15), practice=practice))
    return p


class FlatHeight:
    """A provider with a known, controllable canopy height."""

    name = "flat"

    def __init__(self, by_year, sigma=0.0):
        self.by_year = by_year
        self.sigma = sigma

    def retrieve(self, plot, variable, on):
        if variable != "canopy_height_m":
            return None
        h = self.by_year.get(on.year)
        if h is None:
            return None
        return Retrieval(plot.id, variable, h, "m", self.sigma, on, self.name)


class FixedConfidence:
    name = "fixed"

    def __init__(self, confidence):
        self.confidence = confidence

    def retrieve(self, plot, variable, on):
        if variable != "practice_adopted":
            return None
        return Retrieval(plot.id, variable, self.confidence, "probability",
                         0.1, on, self.name)


# --- VM0047 -----------------------------------------------------------------

def test_vm0047_credits_growth_net_of_the_benchmark():
    """With a perfect allometry and no buffer, credits are exactly the growth."""
    p = build(n=2)
    exact = Allometry(relative_error=0.0)
    m = methodology.get("VM0047", buffer_fraction=0.0, allometry=exact,
                        benchmark=PerformanceBenchmark(t_co2e_per_ha_yr=0.0))
    r = m.quantify(p, FlatHeight({2026: 5.0, 2027: 6.0}), 2027)

    per_ha = (co2e_per_ha(6.0, allometry=exact)[0]
              - co2e_per_ha(5.0, allometry=exact)[0])
    assert r.gross_t == pytest.approx(per_ha * r.area_ha)
    assert r.relative_uncertainty == 0.0
    assert r.net_t == pytest.approx(r.gross_t)


def test_vm0047_generic_allometry_alone_costs_credits():
    """The tree-project equivalent of the Tier 3 argument. A placeholder
    allometry carries 25% error, which is above the 15% allowance, so a
    project pays for it at every verification even with a perfect satellite."""
    p = build(n=2)
    prov = FlatHeight({2026: 5.0, 2027: 6.0}, sigma=0.0)
    bench = PerformanceBenchmark(t_co2e_per_ha_yr=0.0)

    generic = methodology.get("VM0047", buffer_fraction=0.0, benchmark=bench,
                              allometry=Allometry(relative_error=0.25))
    calibrated = methodology.get("VM0047", buffer_fraction=0.0, benchmark=bench,
                                 allometry=Allometry(relative_error=0.10))

    g, c = generic.quantify(p, prov, 2027), calibrated.quantify(p, prov, 2027)
    assert g.gross_t == pytest.approx(c.gross_t)   # same trees
    assert g.net_t < c.net_t                        # fewer credits


def test_vm0047_benchmark_reduces_credits():
    p = build(n=2)
    prov = FlatHeight({2026: 5.0, 2027: 6.0})
    lenient = methodology.get("VM0047", buffer_fraction=0.0,
                              benchmark=PerformanceBenchmark(t_co2e_per_ha_yr=0.0))
    strict = methodology.get("VM0047", buffer_fraction=0.0,
                             benchmark=PerformanceBenchmark(t_co2e_per_ha_yr=5.0))
    assert strict.quantify(p, prov, 2027).gross_t < lenient.quantify(p, prov, 2027).gross_t


def test_vm0047_flags_additionality_when_benchmark_beats_the_project():
    p = build(n=2)
    m = methodology.get("VM0047",
                        benchmark=PerformanceBenchmark(t_co2e_per_ha_yr=10_000.0))
    r = m.quantify(p, FlatHeight({2026: 5.0, 2027: 6.0}), 2027)
    assert r.gross_t == 0.0
    assert any("additionality" in w for w in r.warnings)


def test_vm0047_excludes_ineligible_plots_from_the_area():
    clean = build(n=2)
    dirty = build(n=2, tenure=TenureBasis.UNDOCUMENTED)
    m = methodology.get("VM0047")
    prov = FlatHeight({2026: 5.0, 2027: 6.0})
    assert m.quantify(dirty, prov, 2027).area_ha == 0.0
    assert m.quantify(dirty, prov, 2027).net_t == 0.0
    assert m.quantify(clean, prov, 2027).area_ha > 0.0


def test_vm0047_warns_when_standing_stock_falls():
    p = build(n=1)
    m = methodology.get("VM0047")
    r = m.quantify(p, FlatHeight({2026: 8.0, 2027: 4.0}), 2027)
    assert any("disturbance" in w for w in r.warnings)
    assert r.gross_t == 0.0  # loss is floored, never credited


def test_vm0047_warns_and_skips_when_a_retrieval_is_missing():
    p = build(n=1)
    m = methodology.get("VM0047")
    r = m.quantify(p, FlatHeight({2026: 5.0}), 2027)
    assert r.area_ha == 0.0
    assert any("no canopy retrieval" in w for w in r.warnings)


def test_vm0047_height_uncertainty_costs_real_credits():
    p = build(n=3)
    m = methodology.get("VM0047", buffer_fraction=0.0,
                        benchmark=PerformanceBenchmark(t_co2e_per_ha_yr=0.0))
    precise = m.quantify(p, FlatHeight({2026: 5.0, 2027: 6.0}, sigma=0.0), 2027)
    noisy = m.quantify(p, FlatHeight({2026: 5.0, 2027: 6.0}, sigma=2.0), 2027)
    assert noisy.net_t < precise.net_t
    assert noisy.relative_uncertainty > precise.relative_uncertainty


def test_vm0047_result_serialises_with_its_trail():
    p = build(n=1)
    r = methodology.get("VM0047").quantify(p, FlatHeight({2026: 5.0, 2027: 6.0}), 2027)
    d = r.to_dict()
    assert d["methodology"] == "VM0047"
    assert d["calculations"]
    assert any(c["citations"] for c in d["calculations"])


# --- VM0042 -----------------------------------------------------------------

def test_vm0042_scales_abatement_by_detection_confidence():
    p = build(n=2, practice="awd", track=TrackKind.RICE)
    m = methodology.get("VM0042", buffer_fraction=0.0)
    full = m.quantify(p, FixedConfidence(1.0), 2026)
    part = m.quantify(p, FixedConfidence(0.8), 2026)
    assert part.gross_t == pytest.approx(full.gross_t * 0.8)


def test_vm0042_drops_plots_below_the_confidence_floor():
    p = build(n=2, practice="awd", track=TrackKind.RICE)
    m = methodology.get("VM0042", minimum_confidence=0.5)
    r = m.quantify(p, FixedConfidence(0.3), 2026)
    assert r.gross_t == 0.0
    assert any("confidence" in w for w in r.warnings)


def test_vm0042_warns_on_a_practice_with_no_emission_factor():
    p = build(n=1, practice="moon_farming")
    r = methodology.get("VM0042").quantify(p, FixedConfidence(1.0), 2026)
    assert r.gross_t == 0.0
    assert any("moon_farming" in w for w in r.warnings)


def test_vm0042_tier3_factor_beats_tier1_on_net_credits():
    """The financial case for locally measured emission factors, in one test:
    the same hectares and the same practice, issued at different tiers."""
    p = build(n=3, practice="awd", track=TrackKind.RICE)
    prov = FixedConfidence(1.0)

    def run(tier):
        factors = {"awd": EmissionFactor("awd", 1.6, tier=tier, source="t")}
        return methodology.get("VM0042", factors=factors).quantify(p, prov, 2026)

    t1, t3 = run(1), run(3)
    assert t1.gross_t == pytest.approx(t3.gross_t)     # same physical abatement
    assert t3.net_t > t1.net_t                          # but far more is issuable
    assert t3.net_t / t1.net_t > 1.5


def test_vm0042_only_counts_plots_enrolled_by_the_reporting_year():
    p = build(n=1, practice="awd")
    r = methodology.get("VM0042").quantify(p, FixedConfidence(1.0), 2024)
    assert r.gross_t == 0.0


def test_synthetic_provider_is_deterministic():
    p = build(n=1)
    plot = p.plots["P0"]
    prov = SyntheticProvider(planting_year=2025)
    a = prov.retrieve(plot, "canopy_height_m", date(2030, 12, 31))
    b = prov.retrieve(plot, "canopy_height_m", date(2030, 12, 31))
    assert a.value == b.value


def test_synthetic_provider_has_no_canopy_before_planting():
    p = build(n=1)
    prov = SyntheticProvider(planting_year=2025)
    assert prov.retrieve(p.plots["P0"], "canopy_height_m", date(2024, 12, 31)).value == 0.0
