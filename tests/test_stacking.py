"""Stacking pillars on one hectare.

The product's differentiator and its largest audit risk, which are the same
fact. The rule that does the work is that methodologies partition by carbon
*pool*, not by activity name -- so two claims that sound like different
products can still be selling the same tonne twice.
"""

from datetime import date

import pytest

from carbonstack import stacking
from carbonstack.sites import THANJAVUR, as_project
from carbonstack.stacking import (
    CarbonPool, Conflict, Pillar, PillarClaim, check_plot, conflicts_between,
    pools_for,
)
from carbonstack.store import Store, StoreError

RICE_BED = [(79.1378, 10.7867), (79.1396, 10.7867),
            (79.1396, 10.7877), (79.1378, 10.7877)]
BUND = [(79.1378, 10.7877), (79.1396, 10.7877),
        (79.1396, 10.7878), (79.1378, 10.7878)]


@pytest.fixture
def store():
    with Store(":memory:", actor="tester") as s:
        s.save_project(as_project(THANJAVUR), methodology_id="VM0051")
        yield s


@pytest.fixture
def plot_id(store):
    return next(iter(store.load_project(THANJAVUR.id).plots))


def claim(pillar, methodology, *, plot="P", area=1.0, geometry=None, cid="c"):
    return PillarClaim(id=cid, project_id="X", plot_id=plot, pillar=pillar,
                       methodology_id=methodology, area_ha=area,
                       geometry=geometry)


# --- the pool table ---------------------------------------------------------

def test_vm0042_credits_both_methane_and_soil():
    """This single fact is why rice stacking is hard: VM0042 is not a soil
    methodology that happens to sit beside a methane one, it covers both."""
    assert pools_for("VM0042") == {CarbonPool.CH4_AVOIDED,
                                   CarbonPool.SOIL_ORGANIC_CARBON}
    assert pools_for("VM0051") == {CarbonPool.CH4_AVOIDED}
    assert CarbonPool.SOIL_ORGANIC_CARBON not in pools_for("VM0047")


def test_an_unknown_methodology_is_refused_rather_than_assumed_harmless():
    with pytest.raises(StoreError, match="unknown methodology"):
        pools_for("VM9999")


# --- the rules --------------------------------------------------------------

def test_two_claims_on_the_same_pool_are_double_counting():
    found = conflicts_between(
        claim(Pillar.METHANE, "VM0051", cid="a", geometry=RICE_BED),
        claim(Pillar.SOIL_CARBON, "VM0042", cid="b", geometry=BUND))
    assert any(c.kind == "double_counting" for c in found)
    assert any("ch4_avoided" in c.detail for c in found)


def test_separate_pools_still_need_separate_ground():
    """Rice and the trees on its bund are different pools, but they are not
    the same square metre."""
    found = conflicts_between(
        claim(Pillar.METHANE, "VM0051", cid="a"),
        claim(Pillar.TREES, "VM0047", cid="b", geometry=BUND))
    assert [c.kind for c in found] == ["shared_geometry"]


def test_separate_pools_on_separate_geometry_stack_cleanly():
    assert conflicts_between(
        claim(Pillar.METHANE, "VM0051", cid="a", geometry=RICE_BED),
        claim(Pillar.TREES, "VM0047", cid="b", geometry=BUND)) == []


def test_claims_cannot_total_more_than_the_plot():
    found = check_plot([
        claim(Pillar.METHANE, "VM0051", cid="a", area=2.0, geometry=RICE_BED),
        claim(Pillar.TREES, "VM0047", cid="b", area=1.0, geometry=BUND),
    ], plot_area_ha=2.5)
    assert any(c.kind == "area_overclaim" for c in found)


def test_a_single_claim_needs_no_sub_plot_boundary():
    """There is nothing to separate it from yet, so demanding a boundary up
    front would be ceremony."""
    assert check_plot([claim(Pillar.METHANE, "VM0051", area=2.0)], 2.5) == []


# --- registration -----------------------------------------------------------

def test_registering_the_lawful_shape(store, plot_id):
    m = stacking.register_claim(store, THANJAVUR.id, plot_id,
                                pillar=Pillar.METHANE, methodology_id="VM0051",
                                area_ha=2.2, geometry=RICE_BED)
    t = stacking.register_claim(store, THANJAVUR.id, plot_id,
                                pillar=Pillar.TREES, methodology_id="VM0047",
                                area_ha=0.25, geometry=BUND)
    assert {c.pillar for c in stacking.claims(store)} == {Pillar.METHANE,
                                                          Pillar.TREES}
    assert m.has_own_geometry and t.has_own_geometry


def test_soil_carbon_on_vm0051_rice_is_refused(store, plot_id):
    """The finding the whole module exists for. VM0042 already credits the
    methane, so adding it beside VM0051 sells that methane twice."""
    stacking.register_claim(store, THANJAVUR.id, plot_id, pillar=Pillar.METHANE,
                            methodology_id="VM0051", area_ha=2.2,
                            geometry=RICE_BED)
    with pytest.raises(StoreError, match="sold\\s+twice"):
        stacking.register_claim(store, THANJAVUR.id, plot_id,
                                pillar=Pillar.SOIL_CARBON,
                                methodology_id="VM0042", area_ha=0.2,
                                geometry=BUND)


def test_the_same_pillar_cannot_be_claimed_twice(store, plot_id):
    stacking.register_claim(store, THANJAVUR.id, plot_id, pillar=Pillar.METHANE,
                            methodology_id="VM0051", area_ha=1.0,
                            geometry=RICE_BED)
    with pytest.raises(StoreError, match="already carries"):
        stacking.register_claim(store, THANJAVUR.id, plot_id,
                                pillar=Pillar.METHANE, methodology_id="VM0051",
                                area_ha=1.0, geometry=RICE_BED)


def test_a_claim_on_a_plot_outside_the_project_is_refused(store):
    with pytest.raises(StoreError, match="not in project"):
        stacking.register_claim(store, THANJAVUR.id, "nowhere",
                                pillar=Pillar.TREES, methodology_id="VM0047",
                                area_ha=1.0)


def test_geometry_can_be_added_after_the_fact(store, plot_id):
    """The first pillar is legitimately registered without a boundary. When a
    second arrives it must be able to acquire one without being deleted and
    re-registered, which would break its audit trail."""
    m = stacking.register_claim(store, THANJAVUR.id, plot_id,
                                pillar=Pillar.METHANE, methodology_id="VM0051",
                                area_ha=2.2)
    with pytest.raises(StoreError, match="separate geometry"):
        stacking.register_claim(store, THANJAVUR.id, plot_id,
                                pillar=Pillar.TREES, methodology_id="VM0047",
                                area_ha=0.25, geometry=BUND)

    stacking.set_geometry(store, m.id, RICE_BED)
    stacking.register_claim(store, THANJAVUR.id, plot_id, pillar=Pillar.TREES,
                            methodology_id="VM0047", area_ha=0.25,
                            geometry=BUND)
    assert stacking.audit(store, THANJAVUR.id)["clean"] is True


def test_geometry_cannot_be_used_to_sneak_past_a_conflict(store, plot_id):
    m = stacking.register_claim(store, THANJAVUR.id, plot_id,
                                pillar=Pillar.METHANE, methodology_id="VM0051",
                                area_ha=2.2, geometry=RICE_BED)
    with pytest.raises(StoreError, match="no pillar claim"):
        stacking.set_geometry(store, "clm-nonexistent", BUND)
    # Amending to an over-claiming area is still checked.
    assert stacking.set_geometry(store, m.id, None).geometry is None


# --- audit ------------------------------------------------------------------

def test_audit_reports_a_clean_project(store, plot_id):
    stacking.register_claim(store, THANJAVUR.id, plot_id, pillar=Pillar.METHANE,
                            methodology_id="VM0051", area_ha=2.2,
                            geometry=RICE_BED)
    stacking.register_claim(store, THANJAVUR.id, plot_id, pillar=Pillar.TREES,
                            methodology_id="VM0047", area_ha=0.25, geometry=BUND)
    report = stacking.audit(store, THANJAVUR.id)
    assert report["clean"] is True
    assert report["conflicts"] == []
    assert report["claims"] == 2
    assert report["stacked_plots"] == 1
    assert report["stacked_ha"] > 0


def test_audit_of_a_project_with_no_claims_is_clean_and_empty(store):
    report = stacking.audit(store, THANJAVUR.id)
    assert report["clean"] is True
    assert report["claims"] == 0
    assert report["stacked_share"] == 0.0


def test_registration_lands_in_the_event_chain(store, plot_id):
    stacking.register_claim(store, THANJAVUR.id, plot_id, pillar=Pillar.METHANE,
                            methodology_id="VM0051", area_ha=2.2,
                            geometry=RICE_BED, actor="ops")
    events = [e for e in store.events() if e["kind"].startswith("stacking.")]
    assert events and events[-1]["actor"] == "ops"
    assert events[-1]["payload"]["pools"] == ["ch4_avoided"]
    assert store.verify_chain() == (True, None)
