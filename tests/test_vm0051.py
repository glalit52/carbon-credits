"""VM0051, the purpose-built rice methodology.

The prototype quantified paddy under VM0042. Two independent methodology
reviews flagged that as wrong: VM0051 is written for rice, replaces CDM
AMS-III.AU in the VCS Program, and is CORSIA eligible. These tests pin the
three behaviours that make it a different answer, not just a different name.
"""

from datetime import date

import pytest

from carbonstack import methodology
from carbonstack.domain import (
    CarbonRights, Enrollment, Farmer, Plot, Project, RiceEcosystem,
    StakeholderConsultation, TenureBasis, TrackKind, WaterControl,
)
from carbonstack.methodology.vm0051 import (
    CH4_GWP100, CommonPractice, DEFAULT_RICE_FACTORS, RiceEmissionFactor,
)
from carbonstack.remote_sensing import Retrieval


def square(lon, lat, side=0.003):
    return [(lon, lat), (lon + side, lat), (lon + side, lat + side), (lon, lat + side)]


def build(n=2, *, ecosystem=RiceEcosystem.IRRIGATED_LOWLAND,
          water=WaterControl.FULL, practice="awd"):
    p = Project(id="R1", name="rice", track=TrackKind.RICE, country="IN",
                start_date=date(2025, 6, 1), methodology_version="VM0051 v1.1",
                consultation=StakeholderConsultation(
                    held_on=date(2025, 4, 1), record_reference="C/1",
                    participants=40, grievance_channel="village committee"))
    for i in range(n):
        f = p.add_farmer(Farmer(
            id=f"F{i}", name="A", village="V", district="D", state="Tamil Nadu",
            consent_on=date(2025, 5, 1), consent_reference=f"C/{i}",
            carbon_rights=CarbonRights(agreement_reference=f"CRA/{i}",
                                       signed_on=date(2025, 5, 1),
                                       holder="proponent",
                                       reversal_clause_ack=True)))
        plot = p.add_plot(Plot(id=f"P{i}", farmer_id=f.id,
                               boundary=square(79.13 + i * 0.01, 10.78),
                               tenure=TenureBasis.OWNED_TITLE,
                               tenure_reference="RoR/1"))
        p.enroll(Enrollment(plot_id=plot.id, project_id=p.id,
                            enrolled_on=date(2025, 6, 10), practice=practice,
                            baseline_captured_on=date(2025, 5, 10),
                            practice_started_on=date(2025, 6, 20),
                            ecosystem=ecosystem, water_control=water))
    return p


class Confident:
    name = "fixed"

    def __init__(self, c=1.0):
        self.c = c

    def retrieve(self, plot, variable, on):
        if variable != "practice_adopted":
            return None
        return Retrieval(plot.id, variable, self.c, "probability", 0.05, on, self.name)


def m(**kw):
    kw.setdefault("factors", dict(DEFAULT_RICE_FACTORS))
    kw.setdefault("common_practice",
                  CommonPractice(jurisdiction="Tamil Nadu", awd_penetration=0.04))
    return methodology.get("VM0051", **kw)


# --- identity ---------------------------------------------------------------

def test_vm0051_is_registered_and_versioned():
    assert "VM0051" in methodology.available()
    meth = m()
    assert meth.version == "v1.1"
    assert meth.corsia_eligible is True


def test_vm0051_does_not_credit_soil_carbon():
    """The fact the stacking engine depends on: VM0051 leaves the soil pool
    alone, which is why a separate VM0042 soil claim on the same ground is
    double counting rather than a second product."""
    assert m().credits_soil_carbon is False


# --- eligibility ------------------------------------------------------------

@pytest.mark.parametrize("ecosystem", [
    RiceEcosystem.RAINFED, RiceEcosystem.UPLAND, RiceEcosystem.DEEPWATER,
])
def test_only_irrigated_lowland_rice_is_eligible(ecosystem):
    """The project cannot control the water table on these, and controlling
    it is the intervention."""
    result = m().quantify(build(ecosystem=ecosystem), Confident(), 2026)
    assert result.gross_t == 0.0
    assert result.excluded_plots
    assert any(ecosystem.value in reason
               for reasons in result.excluded_plots.values() for reason in reasons)


def test_irrigation_without_drainage_control_is_not_enough():
    """AWD is draining the field. Being able to fill it is not the same."""
    result = m().quantify(build(water=WaterControl.IRRIGATION_ONLY),
                          Confident(), 2026)
    assert result.gross_t == 0.0
    assert any("drainage control" in reason
               for reasons in result.excluded_plots.values() for reason in reasons)


def test_an_unrecorded_ecosystem_blocks_rather_than_assumes():
    result = m().quantify(build(ecosystem=None, water=None), Confident(), 2026)
    assert result.gross_t == 0.0


def test_eligible_rice_credits():
    result = m().quantify(build(), Confident(), 2026)
    assert result.gross_t > 0
    assert result.net_t > 0
    assert not result.excluded_plots


# --- additionality ----------------------------------------------------------

def test_common_practice_defeats_additionality():
    """Verra rejected a run of rice projects in 2025 on exactly this point, so
    it is a gate and not a note."""
    result = m(common_practice=CommonPractice(
        jurisdiction="Punjab", awd_penetration=0.55)).quantify(
            build(), Confident(), 2026)
    assert result.gross_t == 0.0
    assert result.net_t == 0.0
    assert any("not additional" in w for w in result.warnings)


def test_a_missing_common_practice_assessment_blocks_crediting():
    result = m(common_practice=None).quantify(build(), Confident(), 2026)
    assert result.gross_t == 0.0
    assert any("common-practice" in w for w in result.warnings)


def test_penetration_just_below_the_threshold_still_credits():
    result = m(common_practice=CommonPractice(
        jurisdiction="Tamil Nadu", awd_penetration=0.19, threshold=0.20)
    ).quantify(build(), Confident(), 2026)
    assert result.gross_t > 0


# --- quantification ---------------------------------------------------------

def test_abatement_is_the_methane_delta_at_gwp100():
    f = RiceEmissionFactor(baseline_ch4_kg_ha_season=80.0,
                           project_ch4_kg_ha_season=50.0,
                           seasons_per_year=2.0)
    expected = (80.0 - 50.0) * 2.0 * CH4_GWP100 / 1000.0
    assert f.abatement_t_co2e_ha_yr == pytest.approx(expected)
    assert f.reduction_fraction == pytest.approx(0.375)


def test_a_factor_that_increases_methane_is_refused_at_construction():
    """An increase is not an abatement, and a methodology cannot credit it."""
    with pytest.raises(ValueError, match="not an abatement"):
        RiceEmissionFactor(baseline_ch4_kg_ha_season=40.0,
                           project_ch4_kg_ha_season=60.0)


def test_there_is_no_buffer_pool_on_avoided_methane():
    """Non-permanence applies to a stock that can be released. Avoided methane
    was never stored, so it cannot reverse -- worth about a fifth of the
    credits against an ARR project, and a real difference from VM0042."""
    result = m().quantify(build(), Confident(), 2026)
    buffer = [d for d, _ in result.deductions if d.name == "buffer pool"][0]
    assert buffer.fraction == 0.0
    assert "cannot reverse" in buffer.basis


def test_detection_confidence_scales_the_claim():
    full = m().quantify(build(), Confident(1.0), 2026)
    part = m().quantify(build(), Confident(0.7), 2026)
    assert part.gross_t == pytest.approx(full.gross_t * 0.7)


def test_low_confidence_plots_are_dropped_not_discounted():
    result = m().quantify(build(), Confident(0.2), 2026)
    assert result.gross_t == 0.0
    assert any("confidence" in w for w in result.warnings)


def test_tier_3_factors_issue_more_for_the_same_physical_abatement():
    base = dict(baseline_ch4_kg_ha_season=78.0, project_ch4_kg_ha_season=45.0)
    t1 = m(factors={"awd": RiceEmissionFactor(**base, tier=1)}).quantify(
        build(), Confident(), 2026)
    t3 = m(factors={"awd": RiceEmissionFactor(**base, tier=3)}).quantify(
        build(), Confident(), 2026)
    assert t1.gross_t == pytest.approx(t3.gross_t)
    assert t3.net_t > t1.net_t


def test_an_unknown_practice_contributes_nothing_and_says_so():
    result = m().quantify(build(practice="moon_rice"), Confident(), 2026)
    assert result.gross_t == 0.0
    assert any("moon_rice" in w for w in result.warnings)


def test_the_derivation_cites_the_methodology_and_the_factors():
    result = m().quantify(build(), Confident(), 2026)
    calc = result.calculations[-1]
    joined = " ".join(calc.citations)
    assert "VM0051" in joined
    assert "AMS-III.AU" in joined
    assert "VT0001" in joined
    labels = [t.label for t in calc]
    assert "global warming potential" in labels
    assert "AWD penetration in the jurisdiction" in labels


def test_programme_gaps_surface_as_warnings():
    """An unpinned methodology version or a missing consultation blocks every
    hectare at once, so it is reported on the vintage rather than per plot."""
    p = build()
    p.methodology_version = ""
    p.consultation = None
    result = m().quantify(p, Confident(), 2026)
    assert any("methodology version" in w for w in result.warnings)
    assert any("consultation" in w for w in result.warnings)
