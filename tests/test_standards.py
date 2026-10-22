"""Standards: one tonne, several registries, and what each one leaves.

The comparison is only useful if it refuses the things a registry would
refuse and labels what it does not know, so those are what is tested.
"""

import pytest

from carbonstack.standards import (
    ROUTES, NprtScore, Pathway, Status, compare, routes_for,
)


def test_every_route_tags_its_facts():
    for route in ROUTES.values():
        for fact in route.facts():
            assert isinstance(fact.status, Status), route.id


def test_avoided_methane_is_never_buffered():
    """CH4 was never stored, so it cannot reverse -- under every standard."""
    for route in routes_for(Pathway.RICE):
        assert route.buffer.value == 0.0, route.id


def test_nprt_floor_and_failure():
    assert NprtScore(2, 2, 2).rating.value == pytest.approx(0.12)
    assert NprtScore(10, 6, 4.2).rating.value == pytest.approx(0.21)   # rounded up
    assert NprtScore(10, 21, 4).failures() == [
        "external risk 21 exceeds the NPRT threshold of 20"]


def test_a_failed_nprt_blocks_rather_than_discounts():
    c = compare("arr", gross_t=100, relative_uncertainty=0.1, vintage=2027,
                nprt=NprtScore(40, 5, 5))
    vm0047 = next(o for o in c.outcomes if o.route.id == "vcs-vm0047")
    assert not vm0047.issuable and vm0047.revenue_usd is None


def test_gold_standard_2026_vintages_need_a_paris_aligned_version():
    blocked = compare("soil", gross_t=100, relative_uncertainty=0.1, vintage=2026)
    gs = next(o for o in blocked.outcomes if o.route.id == "gs-soc")
    assert any("Paris-aligned" in b for b in gs.blockers)
    ok = compare("soil", gross_t=100, relative_uncertainty=0.1, vintage=2026,
                 paris_aligned=True)
    gs = next(o for o in ok.outcomes if o.route.id == "gs-soc")
    assert gs.issuable and gs.net_t == pytest.approx(80.0)          # 20% buffer


def test_corsia_for_india_is_blocked_by_the_authorisation_gap():
    c = compare("rice", gross_t=100, relative_uncertainty=0.1, vintage=2026,
                country="India", wants_corsia=True)
    vm0051 = next(o for o in c.outcomes if o.route.id == "vcs-vm0051")
    assert any("Letter of Authorisation" in b for b in vm0051.blockers)
    assert vm0051.leans_on is Status.UNCONFIRMED


def test_an_unknown_buffer_cannot_outrank_a_known_one():
    c = compare("arr", gross_t=1000, relative_uncertainty=0.1, vintage=2026,
                country="Kenya", nprt=NprtScore(8, 6, 4))
    ranked = c.ranked()
    assert ranked[0].route.id == "vcs-vm0047"
    iso = next(o for o in ranked if o.route.id == "isometric-reforestation")
    assert not iso.buffer_known and "<=" in c.render()


def test_biochar_routes_gate_on_h_corg():
    c = compare("biochar", gross_t=100, relative_uncertainty=0.1, vintage=2026,
                biochar_h_corg=0.6)
    by = {o.route.id: o for o in c.outcomes}
    assert by["puro-biochar"].issuable
    assert not by["isometric-biochar"].issuable
    with_ro = compare("biochar", gross_t=100, relative_uncertainty=0.1, vintage=2026,
                      biochar_h_corg=0.6, biochar_random_reflectance=True)
    assert {o.route.id: o for o in with_ro.outcomes}["isometric-biochar"].issuable


def test_domestic_indian_routes_only_appear_for_india():
    kenya = compare("rice", gross_t=10, relative_uncertainty=0.1, vintage=2027, country="Kenya")
    assert "ccts-ag04" not in {o.route.id for o in kenya.outcomes}
    india = compare("rice", gross_t=10, relative_uncertainty=0.1, vintage=2027, country="India")
    ccts = next(o for o in india.outcomes if o.route.id == "ccts-ag04")
    assert ccts.price_usd is None


def test_ccp_label_carries_a_premium():
    c = compare("rice", gross_t=100, relative_uncertainty=0.1, vintage=2027, country="Kenya")
    by = {o.route.id: o for o in c.outcomes}
    assert by["vcs-vm0051"].price_usd > by["isometric-rice"].price_usd
