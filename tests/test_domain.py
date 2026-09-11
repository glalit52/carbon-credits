from datetime import date

import pytest

from carbonstack.domain import (
    Enrollment, Farmer, Observation, Plot, Project, TenureBasis, TrackKind,
)


def square(lon, lat, side=0.003):
    return [(lon, lat), (lon + side, lat), (lon + side, lat + side), (lon, lat + side)]


def make_project(**kw):
    return Project(id="P1", name="demo", track=TrackKind.AGROFORESTRY,
                   country="IN", start_date=date(2025, 7, 1), **kw)


def consented(i=0):
    return Farmer(id=f"F{i}", name="A", village="V", district="D", state="S",
                  consent_on=date(2025, 6, 1), consent_reference=f"C/{i}")


def enrolled_plot(proj, farmer, *, tenure=TenureBasis.OWNED_TITLE,
                  reference="RoR/1", lon=80.0, practice="block_planting"):
    plot = Plot(id=f"PL{lon}", farmer_id=farmer.id, boundary=square(lon, 16.3),
                tenure=tenure, tenure_reference=reference)
    proj.add_plot(plot)
    proj.enroll(Enrollment(plot_id=plot.id, project_id=proj.id,
                           enrolled_on=date(2025, 7, 15), practice=practice))
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
                        enrolled_on=date(2025, 7, 1), practice="x"))
    p.enroll(Enrollment(plot_id="B", project_id="P1",
                        enrolled_on=date(2027, 7, 1), practice="x"))

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
