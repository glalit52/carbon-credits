"""Article 6 authorisation, corresponding adjustments, and the CCTS boundary.

The question here is not how many tonnes but who is allowed to count them.
Getting it wrong does not produce a bad number -- it produces a buyer telling
their regulator something untrue, so every default is the conservative one.
"""

from datetime import date

import pytest

from carbonstack import article6
from carbonstack.article6 import (
    AuthorisedUse, Authorisation, ClaimBasis, CorrespondingAdjustment, classify,
)
from carbonstack.sites import THANJAVUR, as_project
from carbonstack.store import Store, StoreError


def auth(**kw):
    base = dict(
        id="auth-1", project_id="P", authority="MoEFCC, Government of India",
        reference="MoEFCC/A6/2026/0041", issued_on=date(2026, 3, 1),
        authorised_use=AuthorisedUse.CORSIA, authorised_volume_t=50_000.0,
        corresponding_adjustment_committed=True,
        first_vintage=2025, last_vintage=2030)
    base.update(kw)
    return Authorisation(**base)


def adj(volume=100.0, year=2025, authorisation_id="auth-1"):
    return CorrespondingAdjustment(
        id="ca-1", authorisation_id=authorisation_id, project_id="P",
        vintage_year=year, volume_t=volume, applied_on=date(2026, 6, 30),
        reported_in="India BTR 2026, Annex 6.2")


def status(**kw):
    base = dict(project_id="P", vintage_year=2025, issued_t=100.0,
                authorisation=None, adjustments=[])
    base.update(kw)
    return classify(**base)


# --- what a buyer may say ---------------------------------------------------

def test_only_an_adjusted_itmo_permits_an_offsetting_claim():
    """The whole point. Everything else leaves the tonne in someone else's
    account, and counting it twice is what Article 6 exists to prevent."""
    assert ClaimBasis.AUTHORISED_ITMO.permits_offsetting_claim
    assert not ClaimBasis.UNADJUSTED_VOLUNTARY.permits_offsetting_claim
    assert not ClaimBasis.CCTS_DOMESTIC.permits_offsetting_claim


def test_with_no_authorisation_the_buyer_financed_but_did_not_offset():
    s = status()
    assert s.basis is ClaimBasis.UNADJUSTED_VOLUNTARY
    assert s.offsettable_t == 0.0
    assert s.unadjusted_t == 100.0
    assert "may NOT be counted against the buyer's own target" in s.buyer_language


def test_the_buyer_line_reflects_the_adjustment_not_the_basis():
    """An authorisation with no adjustment behind it is still an ITMO by
    basis. A reader who saw only "offset against your target" would make a
    false claim, which is the precise failure this module exists to prevent."""
    promised = status(authorisation=auth(), adjustments=[])
    assert promised.basis is ClaimBasis.AUTHORISED_ITMO
    assert "NOT be counted" in promised.buyer_language

    partial = status(issued_t=100.0, authorisation=auth(),
                     adjustments=[adj(volume=40.0)])
    assert "40.00 tCO2e may be counted" in partial.buyer_language
    assert "60.00 tCO2e have no corresponding adjustment" in partial.buyer_language

    full = status(authorisation=auth(), adjustments=[adj(volume=100.0)])
    assert full.buyer_language.startswith("offset against the buyer's target")


def test_a_promised_adjustment_is_not_an_adjustment():
    """A letter is a promise. Until the host country has actually applied and
    reported it, nothing here may be sold as an offset -- this gap is where
    double claiming really lives."""
    s = status(authorisation=auth(), adjustments=[])
    assert s.basis is ClaimBasis.AUTHORISED_ITMO
    assert s.offsettable_t == 0.0
    assert not s.corsia_eligible
    assert any("none has been applied" in w for w in s.warnings)


def test_an_applied_adjustment_unlocks_the_claim():
    s = status(authorisation=auth(), adjustments=[adj(volume=100.0)])
    assert s.offsettable_t == 100.0
    assert s.unadjusted_t == 0.0
    assert s.corsia_eligible
    assert s.warnings == []


def test_a_partial_adjustment_only_unlocks_what_was_adjusted():
    s = status(issued_t=100.0, authorisation=auth(), adjustments=[adj(volume=40.0)])
    assert s.offsettable_t == 40.0
    assert s.unadjusted_t == 60.0
    assert any("60.00 t of 100.00 t issued have no corresponding adjustment"
               in w for w in s.warnings)


def test_an_authorisation_without_a_ca_commitment_does_not_permit_offsetting():
    s = status(authorisation=auth(corresponding_adjustment_committed=False),
               adjustments=[adj()])
    assert s.basis is ClaimBasis.UNADJUSTED_VOLUNTARY
    assert s.offsettable_t == 0.0
    assert any("does not commit to a corresponding adjustment" in r
               for r in s.reasons)


def test_an_authorisation_that_does_not_cover_the_vintage_is_ignored():
    s = status(vintage_year=2033, authorisation=auth(), adjustments=[])
    assert s.basis is ClaimBasis.UNADJUSTED_VOLUNTARY
    assert any("not 2033" in r for r in s.reasons)


def test_a_revoked_authorisation_says_so_rather_than_vanishing():
    """A buyer asking why their credits stopped being offsettable deserves the
    reason, not "no authorisation on record"."""
    s = status(authorisation=auth(revoked_on=date(2026, 9, 1)),
               adjustments=[adj()], on=date(2026, 10, 1))
    assert s.offsettable_t == 0.0
    assert s.authorisation is not None
    assert any("not live" in r for r in s.reasons)
    assert any("revoked" in w for w in s.warnings)


def test_an_expired_authorisation_stops_permitting_claims():
    s = status(authorisation=auth(valid_until=date(2026, 6, 30)),
               adjustments=[adj()], on=date(2026, 12, 1))
    assert s.offsettable_t == 0.0


def test_corsia_needs_an_authorisation_that_names_corsia():
    other = status(authorisation=auth(authorised_use=AuthorisedUse.OTHER_PARTY_NDC),
                   adjustments=[adj()])
    assert other.offsettable_t == 100.0      # still a valid offset
    assert not other.corsia_eligible         # but not for an airline


def test_adjustments_beyond_the_authorised_volume_are_flagged():
    s = status(issued_t=80_000.0, authorisation=auth(authorised_volume_t=1_000.0),
               adjustments=[adj(volume=5_000.0)])
    assert any("against an authorised volume" in w for w in s.warnings)


def test_an_adjustment_with_no_authorisation_behind_it_is_not_trusted():
    s = status(authorisation=None, adjustments=[adj(volume=100.0)])
    assert s.offsettable_t == 0.0
    assert any("no authorisation behind it" in w for w in s.warnings)


# --- the CCTS boundary ------------------------------------------------------

def test_ccts_registration_without_authorisation_is_domestic_only():
    s = status(ccts_registered=True)
    assert s.basis is ClaimBasis.CCTS_DOMESTIC
    assert "not for international transfer" in s.buyer_language


def test_ccts_plus_international_authorisation_demands_a_check():
    """The same tonne cannot sit in India's scheme and be exported as an ITMO.
    The code cannot see the CCTS registry, so it insists somebody confirms."""
    s = status(authorisation=auth(), adjustments=[adj()], ccts_registered=True)
    assert any("cancelled or never issued" in w for w in s.warnings)


# --- the authorisation record itself ----------------------------------------

def test_an_authorisation_missing_its_basics_is_refused():
    assert any("letter reference" in p for p in auth(reference=" ").issues())
    assert any("issuing authority" in p for p in auth(authority=" ").issues())
    assert any("no volume" in p for p in auth(authorised_volume_t=0).issues())
    assert any("backwards" in p
               for p in auth(first_vintage=2030, last_vintage=2025).issues())


def test_corsia_use_without_a_ca_commitment_is_contradictory():
    problems = auth(authorised_use=AuthorisedUse.CORSIA,
                    corresponding_adjustment_committed=False).issues()
    assert any("CORSIA use requires a corresponding adjustment" in p
               for p in problems)


def test_an_unreported_adjustment_cannot_be_verified():
    a = CorrespondingAdjustment(
        id="ca", authorisation_id="auth-1", project_id="P", vintage_year=2025,
        volume_t=10.0, applied_on=date(2026, 6, 30), reported_in="  ")
    assert any("transparency report" in p for p in a.issues())


# --- persistence ------------------------------------------------------------

@pytest.fixture
def store():
    with Store(":memory:", actor="tester") as s:
        s.save_project(as_project(THANJAVUR), methodology_id="VM0051")
        yield s


def test_authorisation_and_adjustment_round_trip(store):
    a = article6.record_authorisation(
        store, THANJAVUR.id, authority="MoEFCC", reference="REF/1",
        issued_on=date(2026, 3, 1), authorised_use=AuthorisedUse.CORSIA,
        authorised_volume_t=5_000.0, corresponding_adjustment_committed=True,
        first_vintage=2025, last_vintage=2030, actor="legal")
    article6.record_adjustment(store, a.id, vintage_year=2025, volume_t=120.0,
                               applied_on=date(2026, 6, 30),
                               reported_in="BTR 2026", actor="legal")

    assert [x.reference for x in article6.authorisations(store, THANJAVUR.id)] == ["REF/1"]
    assert article6.adjustments(store, THANJAVUR.id)[0].volume_t == 120.0


def test_a_malformed_authorisation_is_refused_at_the_door(store):
    with pytest.raises(StoreError, match="letter reference"):
        article6.record_authorisation(
            store, THANJAVUR.id, authority="MoEFCC", reference="  ",
            issued_on=date(2026, 3, 1), authorised_use=AuthorisedUse.CORSIA,
            authorised_volume_t=1.0, corresponding_adjustment_committed=True,
            first_vintage=2025, last_vintage=2030)


def test_an_adjustment_outside_the_authorised_vintages_is_refused(store):
    a = article6.record_authorisation(
        store, THANJAVUR.id, authority="MoEFCC", reference="REF/1",
        issued_on=date(2026, 3, 1), authorised_use=AuthorisedUse.CORSIA,
        authorised_volume_t=5_000.0, corresponding_adjustment_committed=True,
        first_vintage=2025, last_vintage=2026)
    with pytest.raises(StoreError, match="not 2031"):
        article6.record_adjustment(store, a.id, vintage_year=2031,
                                   volume_t=10.0, applied_on=date(2032, 1, 1),
                                   reported_in="BTR")


def test_revoking_twice_is_refused(store):
    a = article6.record_authorisation(
        store, THANJAVUR.id, authority="MoEFCC", reference="REF/1",
        issued_on=date(2026, 3, 1), authorised_use=AuthorisedUse.CORSIA,
        authorised_volume_t=5_000.0, corresponding_adjustment_committed=True,
        first_vintage=2025, last_vintage=2030)
    article6.revoke_authorisation(store, a.id, on=date(2026, 9, 1),
                                  reason="policy change")
    with pytest.raises(StoreError, match="already revoked"):
        article6.revoke_authorisation(store, a.id, on=date(2026, 10, 1),
                                      reason="again")


def test_article6_work_lands_in_the_event_chain(store):
    a = article6.record_authorisation(
        store, THANJAVUR.id, authority="MoEFCC", reference="REF/1",
        issued_on=date(2026, 3, 1), authorised_use=AuthorisedUse.CORSIA,
        authorised_volume_t=5_000.0, corresponding_adjustment_committed=True,
        first_vintage=2025, last_vintage=2030, actor="legal")
    article6.record_adjustment(store, a.id, vintage_year=2025, volume_t=10.0,
                               applied_on=date(2026, 6, 30),
                               reported_in="BTR", actor="legal")
    article6.revoke_authorisation(store, a.id, on=date(2026, 9, 1),
                                  reason="policy", actor="legal")

    kinds = [e["kind"] for e in store.events() if e["kind"].startswith("article6.")]
    assert kinds == ["article6.authorised", "article6.adjustment_applied",
                     "article6.revoked"]
    assert store.verify_chain() == (True, None)


def test_claim_register_on_a_project_with_no_issuance_is_empty(store):
    register = article6.claim_register(store, THANJAVUR.id)
    assert register["vintages"] == []
    assert register["offsettable_t"] == 0.0
    assert register["clean"] is True
