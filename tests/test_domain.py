from datetime import date

import pytest

from carbonstack.domain import (
    CarbonRights, Enrollment, Farmer, Observation, Plot, Project, TenureBasis,
    TrackKind,
)


def square(lon, lat, side=0.003):
    return [(lon, lat), (lon + side, lat), (lon + side, lat + side), (lon, lat + side)]


def make_project(**kw):
    return Project(id="P1", name="demo", track=TrackKind.AGROFORESTRY,
                   country="IN", start_date=date(2025, 7, 1), **kw)


def consented(i=0):
    """A farmer who clears every gate: data consent AND carbon rights."""
    return Farmer(id=f"F{i}", name="A", village="V", district="D", state="S",
                  consent_on=date(2025, 6, 1), consent_reference=f"C/{i}",
                  carbon_rights=CarbonRights(
                      agreement_reference=f"CRA/{i}",
                      signed_on=date(2025, 6, 1), holder="proponent",
                      reversal_clause_ack=True))


def enrolled_plot(proj, farmer, *, tenure=TenureBasis.OWNED_TITLE,
                  reference="RoR/1", lon=80.0, practice="block_planting"):
    plot = Plot(id=f"PL{lon}", farmer_id=farmer.id, boundary=square(lon, 16.3),
                tenure=tenure, tenure_reference=reference)
    proj.add_plot(plot)
    proj.enroll(Enrollment(plot_id=plot.id, project_id=proj.id,
                           enrolled_on=date(2025, 7, 15), practice=practice,
                           baseline_captured_on=date(2025, 6, 20),
                           practice_started_on=date(2025, 7, 15)))
    return plot


def test_plot_requires_a_known_farmer():
    p = make_project()
    with pytest.raises(KeyError):
        p.add_plot(Plot(id="X", farmer_id="nobody", boundary=square(80, 16),
                        tenure=TenureBasis.OWNED_TITLE))


def test_enrolment_requires_a_known_plot():
    p = make_project()
    with pytest.raises(KeyError):
        p.enroll(Enrollment(plot_id="X", project_id="P1",
                            enrolled_on=date(2025, 1, 1), practice="awd"))


def test_undocumented_tenure_blocks_crediting():
    p = make_project()
    f = p.add_farmer(consented())
    plot = enrolled_plot(p, f, tenure=TenureBasis.UNDOCUMENTED, reference="")
    assert plot.id in p.eligibility_issues()
    assert plot.id not in p.creditable_plot_ids()
    assert p.creditable_area_ha() == 0.0


def test_tenure_without_a_reference_document_blocks_crediting():
    p = make_project()
    f = p.add_farmer(consented())
    plot = enrolled_plot(p, f, reference="")
    assert any("no reference document" in m for m in p.eligibility_issues()[plot.id])


def test_missing_consent_blocks_crediting():
    p = make_project()
    f = p.add_farmer(Farmer(id="F9", name="A", village="V", district="D", state="S"))
    plot = enrolled_plot(p, f)
    assert any("consent" in m for m in p.eligibility_issues()[plot.id])


def test_clean_plot_is_creditable_and_counts_area():
    p = make_project()
    f = p.add_farmer(consented())
    plot = enrolled_plot(p, f)
    assert p.eligibility_issues() == {}
    assert p.creditable_plot_ids() == {plot.id}
    assert p.creditable_area_ha() == pytest.approx(plot.area_ha)


def test_fingerprint_changes_when_a_boundary_is_redrawn():
    """Silent boundary growth between vintages is an easy way to over-credit
    without anyone deciding to. The fingerprint makes it detectable."""
    p = make_project()
    f = p.add_farmer(consented())
    plot = enrolled_plot(p, f)
    before = plot.fingerprint
    plot.boundary = square(80.0, 16.3, side=0.004)
    assert plot.fingerprint != before


def test_cohorts_group_by_enrolment_year_and_age_together():
    p = make_project()
    f = p.add_farmer(consented())
    a = Plot(id="A", farmer_id=f.id, boundary=square(80, 16),
             tenure=TenureBasis.OWNED_TITLE, tenure_reference="R")
    b = Plot(id="B", farmer_id=f.id, boundary=square(81, 16),
             tenure=TenureBasis.OWNED_TITLE, tenure_reference="R")
    p.add_plot(a)
    p.add_plot(b)
    p.enroll(Enrollment(plot_id="A", project_id="P1",
                        enrolled_on=date(2025, 7, 1), practice="x",
                        baseline_captured_on=date(2025, 6, 1)))
    p.enroll(Enrollment(plot_id="B", project_id="P1",
                        enrolled_on=date(2027, 7, 1), practice="x",
                        baseline_captured_on=date(2027, 6, 1)))

    cohorts = p.cohorts()
    assert [c.year for c in cohorts] == [2025, 2027]
    assert cohorts[0].age_in(2030) == 6
    assert cohorts[1].age_in(2030) == 4
    assert cohorts[1].age_in(2026) == 0


def test_latest_observation_respects_the_cutoff_date():
    p = make_project()
    f = p.add_farmer(consented())
    plot = enrolled_plot(p, f)
    for yr, val in ((2026, 3.0), (2027, 5.0), (2028, 7.0)):
        p.observe(Observation(plot_id=plot.id, observed_on=date(yr, 12, 31),
                              variable="canopy_height_m", value=val, unit="m",
                              source="sentinel2+gedi"))
    assert p.latest_observation(plot.id, "canopy_height_m").value == 7.0
    assert p.latest_observation(plot.id, "canopy_height_m",
                               on_or_before=date(2027, 12, 31)).value == 5.0
    assert p.latest_observation(plot.id, "soc_pct") is None


def test_observation_requires_a_known_plot():
    p = make_project()
    with pytest.raises(KeyError):
        p.observe(Observation(plot_id="nope", observed_on=date(2026, 1, 1),
                              variable="x", value=1.0, unit="m", source="s"))


# --- registry-blocking records the first schema had no room for -------------

def test_data_consent_is_not_carbon_rights():
    """The gap a methodology review found: enrolment captured permission to
    use data and called it done, leaving the project unable to show a registry
    who owns the carbon."""
    from carbonstack.domain import CarbonRights

    p = make_project()
    f = p.add_farmer(Farmer(id="F1", name="A", village="V", district="D",
                            state="S", consent_on=date(2025, 6, 1),
                            consent_reference="C/1"))
    plot = enrolled_plot(p, f)
    assert f.consent_valid                       # data consent is fine
    assert "no carbon rights agreement on file" in p.eligibility_issues()[plot.id]

    f.carbon_rights = CarbonRights(agreement_reference="CRA/1",
                                   signed_on=date(2025, 6, 1),
                                   holder="proponent", reversal_clause_ack=True)
    assert p.eligibility_issues() == {}


def test_a_farmer_must_be_told_what_a_reversal_means():
    """AFOLU credits carry a buffer and can be reversed. A farmer who has not
    acknowledged that has not really agreed to the deal."""
    from carbonstack.domain import CarbonRights

    rights = CarbonRights(agreement_reference="CRA/1", signed_on=date(2025, 6, 1),
                          holder="proponent", reversal_clause_ack=False)
    assert any("reversal" in m for m in rights.issues())


def test_an_expired_carbon_rights_agreement_blocks(tmp_path):
    from carbonstack.domain import CarbonRights

    rights = CarbonRights(agreement_reference="CRA/1", signed_on=date(2020, 1, 1),
                          holder="proponent", reversal_clause_ack=True,
                          expires_on=date(2024, 1, 1))
    assert any("expired" in m for m in rights.issues(on=date(2026, 1, 1)))
    assert rights.issues(on=date(2023, 1, 1)) == []


def test_a_practice_adopted_before_the_baseline_breaks_additionality():
    """The eligible pool shrinks every season this is not captured: a farmer
    already practising AWD has no counterfactual left to measure."""
    p = make_project()
    f = p.add_farmer(consented())
    plot = Plot(id="PL", farmer_id=f.id, boundary=square(80.0, 16.3),
                tenure=TenureBasis.OWNED_TITLE, tenure_reference="RoR/1")
    p.add_plot(plot)
    p.enroll(Enrollment(plot_id=plot.id, project_id=p.id,
                        enrolled_on=date(2025, 7, 15), practice="awd",
                        baseline_captured_on=date(2025, 6, 20),
                        practice_started_on=date(2024, 6, 1)))
    problems = p.eligibility_issues()[plot.id]
    assert any("additionality is at risk" in m for m in problems)


def test_a_missing_baseline_date_blocks_on_its_own():
    p = make_project()
    f = p.add_farmer(consented())
    plot = Plot(id="PL", farmer_id=f.id, boundary=square(80.0, 16.3),
                tenure=TenureBasis.OWNED_TITLE, tenure_reference="RoR/1")
    p.add_plot(plot)
    p.enroll(Enrollment(plot_id=plot.id, project_id=p.id,
                        enrolled_on=date(2025, 7, 15), practice="awd"))
    assert any("baseline capture date" in m
               for m in p.eligibility_issues()[plot.id])


def test_programme_issues_are_reported_once_not_per_plot():
    """An unpinned methodology version blocks every hectare at once, so
    repeating it against each plot would bury the per-plot findings."""
    from carbonstack.domain import StakeholderConsultation

    p = make_project()
    f = p.add_farmer(consented())
    enrolled_plot(p, f)
    problems = p.programme_issues()
    assert any("methodology version" in m for m in problems)
    assert any("consultation" in m for m in problems)
    assert p.eligibility_issues() == {}          # the plot itself is fine

    p.methodology_version = "VM0051 v1.1"
    p.consultation = StakeholderConsultation(
        held_on=date(2025, 4, 1), record_reference="C/1", participants=40,
        grievance_channel="village committee, monthly")
    assert p.programme_issues() == []


def test_a_consultation_with_no_grievance_channel_is_incomplete():
    from carbonstack.domain import StakeholderConsultation

    c = StakeholderConsultation(held_on=date(2025, 4, 1), record_reference="C/1",
                                participants=40)
    assert any("grievance" in m for m in c.issues())


def test_rice_ecosystem_eligibility_is_explicit():
    from carbonstack.domain import RiceEcosystem, WaterControl

    assert RiceEcosystem.IRRIGATED_LOWLAND.vm0051_eligible
    for bad in (RiceEcosystem.RAINFED, RiceEcosystem.UPLAND,
                RiceEcosystem.DEEPWATER, RiceEcosystem.UNKNOWN):
        assert not bad.vm0051_eligible
    assert WaterControl.FULL.sufficient_for_awd
    assert not WaterControl.IRRIGATION_ONLY.sufficient_for_awd
