from datetime import date, timedelta

import pytest

from carbonstack import ledger, payments
from carbonstack.ledger import VintageStatus
from carbonstack.methodology.base import Deduction, VintageResult
from carbonstack.sites import THANJAVUR, as_project
from carbonstack.store import Store, StoreError


def result(project_id="IN-TNJ-01", year=2025, gross=10.0, net=7.4,
           warnings=None, area=2.492):
    r = VintageResult(project_id=project_id, methodology="VM0042", year=year,
                      area_ha=area, gross_t=gross, net_t=net,
                      relative_uncertainty=0.5)
    r.deductions = [
        (Deduction("uncertainty", 0.35, "tier 1"), gross * 0.35),
        (Deduction("buffer pool", 0.15, "reversal risk"), gross * 0.65 * 0.15),
    ]
    r.warnings = list(warnings or [])
    return r


@pytest.fixture
def store():
    with Store(":memory:", actor="tester") as s:
        s.save_project(as_project(THANJAVUR), methodology_id="VM0042")
        yield s


def approved(store, **kw):
    v = ledger.record_vintage(store, result(**kw))
    ledger.submit_for_review(store, v.id, actor="a")
    return ledger.approve(store, v.id, actor="b", note="ok")


# --- whole tonnes -----------------------------------------------------------

def test_credits_are_issued_in_whole_tonnes_and_the_fraction_is_carried():
    """Registries do not issue 1.8 credits. The fraction must be recorded as a
    carry, not quietly dropped -- dropping it is a rounding bug that only shows
    up as a slow shortfall against a delivery contract."""
    v = ledger.Vintage(
        id="x:2025", project_id="x", year=2025, methodology_id="VM0042",
        area_ha=2.5, gross_t=2.1, net_t=1.7997, relative_uncertainty=0.12,
        deductions=[], warnings=[], status=VintageStatus.DRAFT,
        quantified_at="now")
    assert v.issuable_whole == 1
    assert v.carry == pytest.approx(0.7997, abs=1e-4)


def test_a_vintage_below_one_tonne_issues_nothing(store):
    v = approved(store, gross=0.9, net=0.6)
    with pytest.raises(StoreError, match="rounds to zero"):
        ledger.issue(store, v.id, registry="GS", actor="b")


# --- the state machine ------------------------------------------------------

def test_a_new_vintage_starts_as_a_draft(store):
    assert ledger.record_vintage(store, result()).status is VintageStatus.DRAFT


def test_issuing_a_draft_is_refused(store):
    v = ledger.record_vintage(store, result())
    with pytest.raises(StoreError, match="only an approved vintage"):
        ledger.issue(store, v.id, registry="GS", actor="b")


def test_approving_straight_from_draft_is_refused(store):
    """Quantify-and-issue in one step is no control at all, so the machine
    makes review a separate act."""
    v = ledger.record_vintage(store, result())
    with pytest.raises(StoreError, match="can move to"):
        ledger.approve(store, v.id, actor="b", note="ok")


def test_approving_a_warned_vintage_needs_a_written_reason(store):
    v = ledger.record_vintage(store, result(warnings=["no dry-down detected"]))
    ledger.submit_for_review(store, v.id, actor="a")
    with pytest.raises(StoreError, match="requires a note"):
        ledger.approve(store, v.id, actor="b")
    assert ledger.approve(store, v.id, actor="b",
                          note="farmer confirmed by phone").status \
        is VintageStatus.APPROVED


def test_a_held_vintage_can_go_back_for_review(store):
    v = ledger.record_vintage(store, result())
    ledger.submit_for_review(store, v.id, actor="a")
    ledger.hold(store, v.id, actor="b", note="field visit first")
    assert ledger.submit_for_review(store, v.id, actor="a").status \
        is VintageStatus.UNDER_REVIEW


def test_issued_is_terminal(store):
    v = approved(store)
    ledger.issue(store, v.id, registry="GS", actor="b")
    with pytest.raises(StoreError, match="can move to nothing"):
        ledger.hold(store, v.id, actor="b", note="oops")


def test_requantifying_an_issued_vintage_is_refused(store):
    """The issued number is a commercial fact somebody has bought against. A
    recomputation that disagrees is an incident, not an update."""
    v = approved(store)
    ledger.issue(store, v.id, registry="GS", actor="b")
    with pytest.raises(StoreError, match="already issued"):
        ledger.record_vintage(store, result(net=99.0))


def test_requantifying_an_approved_vintage_resets_it_to_draft(store):
    """An approval was given against numbers that no longer exist."""
    v = approved(store)
    again = ledger.record_vintage(store, result(net=8.1))
    assert again.status is VintageStatus.DRAFT
    assert again.net_t == pytest.approx(8.1)


def test_a_cancelled_vintage_cannot_be_revived(store):
    v = ledger.record_vintage(store, result())
    ledger.cancel(store, v.id, actor="b", note="wrong boundary")
    with pytest.raises(StoreError, match="was cancelled"):
        ledger.record_vintage(store, result())


# --- issuance ---------------------------------------------------------------

def test_issuance_allocates_a_contiguous_serial_range(store):
    v = approved(store, gross=100.0, net=74.0)
    iss = ledger.issue(store, v.id, registry="Gold Standard",
                       registry_ref="GS-1", actor="b")
    assert iss.quantity == 74
    assert iss.serial_start.endswith("00000001")
    assert iss.serial_end.endswith("00000074")
    assert iss.registry == "Gold Standard"


def test_the_buffer_contribution_is_tracked_at_issuance(store):
    v = approved(store, gross=100.0, net=74.0)
    ledger.issue(store, v.id, registry="GS", actor="b")
    balance = ledger.buffer_balance(store)
    assert balance["entries"] == 1
    assert balance["held_t"] == pytest.approx(100.0 * 0.65 * 0.15)
    assert balance["released_t"] == 0


def test_buffer_can_be_released_once_only(store):
    v = approved(store, gross=100.0, net=74.0)
    ledger.issue(store, v.id, registry="GS", actor="b")
    entry = store.conn.execute("SELECT id FROM buffer_entries").fetchone()["id"]
    ledger.release_buffer(store, entry, note="crediting period closed", actor="b")
    assert ledger.buffer_balance(store)["held_t"] == 0
    with pytest.raises(StoreError, match="already released"):
        ledger.release_buffer(store, entry, note="again", actor="b")


def test_the_whole_path_is_in_the_event_chain(store):
    v = approved(store, gross=100.0, net=74.0)
    ledger.issue(store, v.id, registry="GS", actor="priya")
    kinds = [e["kind"] for e in store.events("vintage", v.id)]
    assert kinds == ["vintage.quantified", "vintage.under_review",
                     "vintage.approved", "vintage.issued"]
    assert store.verify_chain() == (True, None)
    issued = store.events("vintage", v.id)[-1]
    assert issued["actor"] == "priya"
    assert issued["payload"]["quantity"] == 74


# --- payments ---------------------------------------------------------------

def test_payment_terms_reject_impossible_values():
    with pytest.raises(ValueError):
        payments.PaymentTerms(price_per_credit=12, farmer_share=1.4)
    with pytest.raises(ValueError):
        payments.PaymentTerms(price_per_credit=-1, farmer_share=0.5)


def test_payments_are_only_raised_against_issued_credits(store):
    """Raising against expected credits is how a project ends up owing money
    it has not been paid."""
    v = approved(store, gross=100.0, net=74.0)
    terms = payments.PaymentTerms(price_per_credit=12, farmer_share=0.55)
    with pytest.raises(StoreError, match="issued credits, not expected"):
        payments.raise_payments(store, v.id, terms)


def test_payments_split_the_pool_and_land_in_the_register(store):
    v = approved(store, gross=100.0, net=74.0)
    ledger.issue(store, v.id, registry="GS", actor="b")
    terms = payments.PaymentTerms(price_per_credit=12, farmer_share=0.55)
    made = payments.raise_payments(store, v.id, terms, actor="lalit")

    assert len(made) == 1
    expected_pool = 74 * 12 * 0.55
    assert sum(p.amount for p in made) == pytest.approx(expected_pool, abs=0.05)
    assert made[0].status is payments.PaymentStatus.PENDING


def test_raising_twice_is_refused(store):
    v = approved(store, gross=100.0, net=74.0)
    ledger.issue(store, v.id, registry="GS", actor="b")
    terms = payments.PaymentTerms(price_per_credit=12, farmer_share=0.55)
    payments.raise_payments(store, v.id, terms)
    with pytest.raises(StoreError, match="already has"):
        payments.raise_payments(store, v.id, terms)


def test_an_excluded_plot_earns_its_farmer_nothing_and_says_why(store):
    """The question a field team will actually be asked, and the register has
    to be able to answer it."""
    from carbonstack.domain import TenureBasis

    project = store.load_project("IN-TNJ-01")
    plot = next(iter(project.plots.values()))
    plot.tenure = TenureBasis.UNDOCUMENTED
    plot.tenure_reference = ""
    store.save_project(project, methodology_id="VM0042")

    v = approved(store, gross=100.0, net=74.0)
    ledger.issue(store, v.id, registry="GS", actor="b")
    credits, excluded = payments.allocate(store, ledger.get_vintage(store, v.id))

    assert credits == {}
    assert excluded
    assert any("tenure" in reason for reasons in excluded.values() for reason in reasons)


def test_marking_paid_requires_a_reference(store):
    v = approved(store, gross=100.0, net=74.0)
    ledger.issue(store, v.id, registry="GS", actor="b")
    made = payments.raise_payments(
        store, v.id, payments.PaymentTerms(price_per_credit=12, farmer_share=0.55))
    pid = made[0].id

    payments.approve_payment(store, pid, actor="lalit")
    with pytest.raises(StoreError, match="reference is required"):
        payments.mark_paid(store, pid, reference="   ", actor="lalit")
    p = payments.mark_paid(store, pid, reference="UPI/2026/1", actor="lalit")
    assert p.status is payments.PaymentStatus.PAID
    assert p.reference == "UPI/2026/1"


def test_a_paid_payment_cannot_move_again(store):
    v = approved(store, gross=100.0, net=74.0)
    ledger.issue(store, v.id, registry="GS", actor="b")
    made = payments.raise_payments(
        store, v.id, payments.PaymentTerms(price_per_credit=12, farmer_share=0.55))
    payments.approve_payment(store, made[0].id, actor="l")
    payments.mark_paid(store, made[0].id, reference="R1", actor="l")
    with pytest.raises(StoreError, match="can move to nothing"):
        payments.approve_payment(store, made[0].id, actor="l")


def test_summary_counts_overdue(store):
    v = approved(store, gross=100.0, net=74.0)
    ledger.issue(store, v.id, registry="GS", actor="b")
    payments.raise_payments(
        store, v.id, payments.PaymentTerms(price_per_credit=12, farmer_share=0.55),
        due_on=date.today() - timedelta(days=10))
    s = payments.summary(store, "IN-TNJ-01")
    assert s["overdue_count"] == 1
    assert s["overdue_total"] > 0
    assert s["paid_total"] == 0
