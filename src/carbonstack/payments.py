"""Farmer payments: the half of the product that decides whether anyone stays.

A carbon project that pays late, pays wrong, or cannot explain a payment loses
its farmers, and a project that loses its farmers has no asset. So payments are
a first-class record here, not a spreadsheet somebody keeps.

The allocation rule is pro-rata by **creditable** area, and that word carries
the weight. A plot excluded for missing tenure documents or missing consent
earns its farmer nothing -- which is correct, and is exactly the thing a farmer
will turn up angry about. The register therefore records the excluded farmers
too, with the reason, so the field team can answer the question rather than
discover it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from .ledger import Vintage, get_vintage
from .store.repo import Store, StoreError, _now, new_id


class PaymentStatus(str, Enum):
    PENDING = "pending"      # raised, not yet authorised
    APPROVED = "approved"    # authorised for disbursement
    PAID = "paid"            # money has moved
    FAILED = "failed"        # disbursement bounced


@dataclass(frozen=True)
class PaymentTerms:
    """What a credit is worth and how it splits."""

    price_per_credit: float
    farmer_share: float
    currency: str = "USD"
    payment_days: int = 45

    def __post_init__(self) -> None:
        if not 0 <= self.farmer_share <= 1:
            raise ValueError("farmer_share must be between 0 and 1")
        if self.price_per_credit < 0:
            raise ValueError("price_per_credit cannot be negative")


@dataclass
class Payment:
    id: str
    project_id: str
    farmer_id: str
    vintage_id: str
    credits: float
    amount: float
    currency: str
    status: PaymentStatus
    due_on: date | None
    paid_on: date | None
    reference: str

    def to_dict(self) -> dict:
        return {
            "id": self.id, "project_id": self.project_id,
            "farmer_id": self.farmer_id, "vintage_id": self.vintage_id,
            "credits": round(self.credits, 4), "amount": round(self.amount, 2),
            "currency": self.currency, "status": self.status.value,
            "due_on": self.due_on.isoformat() if self.due_on else None,
            "paid_on": self.paid_on.isoformat() if self.paid_on else None,
            "reference": self.reference,
        }


def _row(r) -> Payment:
    return Payment(
        id=r["id"], project_id=r["project_id"], farmer_id=r["farmer_id"],
        vintage_id=r["vintage_id"], credits=r["credits"], amount=r["amount"],
        currency=r["currency"], status=PaymentStatus(r["status"]),
        due_on=date.fromisoformat(r["due_on"]) if r["due_on"] else None,
        paid_on=date.fromisoformat(r["paid_on"]) if r["paid_on"] else None,
        reference=r["reference"],
    )


def allocate(store: Store, vintage: Vintage) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Split a vintage's credits across farmers by creditable area.

    Returns (credits by farmer, exclusion reasons by farmer). The second half
    matters as much as the first: it is the answer to "why did I get nothing".
    """
    project = store.load_project(vintage.project_id)
    creditable = project.creditable_plot_ids()
    issues = project.eligibility_issues()

    area_by_farmer: dict[str, float] = {}
    for plot_id in creditable:
        plot = project.plots[plot_id]
        area_by_farmer[plot.farmer_id] = area_by_farmer.get(plot.farmer_id, 0.0) + plot.area_ha

    excluded: dict[str, list[str]] = {}
    for plot_id, problems in issues.items():
        farmer_id = project.plots[plot_id].farmer_id
        excluded.setdefault(farmer_id, []).extend(
            f"{plot_id}: {p}" for p in problems)

    total = sum(area_by_farmer.values())
    if total <= 0:
        return {}, excluded

    return (
        {fid: vintage.net_t * ha / total for fid, ha in area_by_farmer.items()},
        excluded,
    )


def raise_payments(store: Store, vintage_id: str, terms: PaymentTerms, *,
                   due_on: date | None = None, actor: str | None = None) -> list[Payment]:
    """Create the payment register for a vintage.

    Only for a vintage that has actually been issued -- raising payments
    against credits that do not exist yet is how a project ends up owing money
    it has not been paid.
    """
    from .ledger import VintageStatus

    v = get_vintage(store, vintage_id)
    if v.status is not VintageStatus.ISSUED:
        raise StoreError(
            f"vintage {vintage_id} is {v.status.value}; payments are raised "
            f"against issued credits, not expected ones")

    existing = store.conn.execute(
        "SELECT COUNT(*) FROM payments WHERE vintage_id = ?", (vintage_id,)).fetchone()[0]
    if existing:
        raise StoreError(
            f"vintage {vintage_id} already has {existing} payment(s) raised; "
            f"cancel them before raising again")

    credits_by_farmer, excluded = allocate(store, v)
    due = due_on or (date.today() + timedelta(days=terms.payment_days))
    pool = v.issuable_whole * terms.price_per_credit * terms.farmer_share
    total_credits = sum(credits_by_farmer.values()) or 1.0

    made: list[Payment] = []
    with store.tx() as conn:
        for farmer_id, credits in sorted(credits_by_farmer.items()):
            amount = round(pool * credits / total_credits, 2)
            p = Payment(
                id=new_id("pay"), project_id=v.project_id, farmer_id=farmer_id,
                vintage_id=vintage_id, credits=credits, amount=amount,
                currency=terms.currency, status=PaymentStatus.PENDING,
                due_on=due, paid_on=None, reference="",
            )
            conn.execute(
                "INSERT INTO payments (id, project_id, farmer_id, vintage_id,"
                " credits, amount, currency, status, due_on, paid_on, reference,"
                " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.id, p.project_id, p.farmer_id, p.vintage_id, p.credits,
                 p.amount, p.currency, p.status.value,
                 due.isoformat(), None, "", _now()))
            made.append(p)

        store.record("payments.raised", "vintage", vintage_id, {
            "farmers_paid": len(made),
            "farmers_excluded": len(excluded),
            "pool": round(pool, 2),
            "currency": terms.currency,
            "price_per_credit": terms.price_per_credit,
            "farmer_share": terms.farmer_share,
            "due_on": due.isoformat(),
        }, actor=actor)
    return made


def approve_payment(store: Store, payment_id: str, *, actor: str | None = None) -> Payment:
    return _move(store, payment_id, PaymentStatus.APPROVED, actor=actor)


def mark_paid(store: Store, payment_id: str, *, reference: str,
              paid_on: date | None = None, actor: str | None = None) -> Payment:
    """Record that money actually moved. A reference is required.

    An unreferenced payment cannot be reconciled against a bank statement, and
    a payment that cannot be reconciled is, for audit purposes, a payment that
    did not happen.
    """
    if not reference.strip():
        raise StoreError("a payment reference is required to mark a payment paid")
    return _move(store, payment_id, PaymentStatus.PAID, reference=reference,
                 paid_on=paid_on or date.today(), actor=actor)


def fail_payment(store: Store, payment_id: str, *, reason: str,
                 actor: str | None = None) -> Payment:
    return _move(store, payment_id, PaymentStatus.FAILED, reference=reason, actor=actor)


_PAYMENT_TRANSITIONS = {
    PaymentStatus.PENDING: {PaymentStatus.APPROVED, PaymentStatus.FAILED},
    PaymentStatus.APPROVED: {PaymentStatus.PAID, PaymentStatus.FAILED},
    PaymentStatus.FAILED: {PaymentStatus.APPROVED},
    PaymentStatus.PAID: set(),
}


def _move(store: Store, payment_id: str, to: PaymentStatus, *,
          reference: str = "", paid_on: date | None = None,
          actor: str | None = None) -> Payment:
    row = store.conn.execute(
        "SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    if row is None:
        raise StoreError(f"no payment {payment_id!r}")
    p = _row(row)
    if to not in _PAYMENT_TRANSITIONS[p.status]:
        allowed = ", ".join(sorted(s.value for s in _PAYMENT_TRANSITIONS[p.status])) or "nothing"
        raise StoreError(
            f"payment {payment_id} is {p.status.value}; it can move to {allowed}, "
            f"not {to.value}")

    with store.tx() as conn:
        conn.execute(
            "UPDATE payments SET status = ?, reference = ?, paid_on = ? WHERE id = ?",
            (to.value, reference or p.reference,
             paid_on.isoformat() if paid_on else (p.paid_on.isoformat() if p.paid_on else None),
             payment_id))
        store.record(f"payment.{to.value}", "payment", payment_id, {
            "from": p.status.value, "farmer_id": p.farmer_id,
            "amount": p.amount, "currency": p.currency,
            "reference": reference,
        }, actor=actor)
    return _row(store.conn.execute(
        "SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone())


def register(store: Store, *, project_id: str | None = None,
             farmer_id: str | None = None,
             status: PaymentStatus | None = None) -> list[Payment]:
    sql, args, where = "SELECT * FROM payments", [], []
    if project_id:
        where.append("project_id = ?")
        args.append(project_id)
    if farmer_id:
        where.append("farmer_id = ?")
        args.append(farmer_id)
    if status:
        where.append("status = ?")
        args.append(status.value)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY due_on, farmer_id"
    return [_row(r) for r in store.conn.execute(sql, args)]


def summary(store: Store, project_id: str | None = None) -> dict:
    """What is owed, what is late, what has been paid."""
    rows = register(store, project_id=project_id)
    today = date.today()
    outstanding = [p for p in rows if p.status in
                   (PaymentStatus.PENDING, PaymentStatus.APPROVED)]
    overdue = [p for p in outstanding if p.due_on and p.due_on < today]
    return {
        "payments": len(rows),
        "farmers": len({p.farmer_id for p in rows}),
        "paid_total": round(sum(p.amount for p in rows
                                if p.status is PaymentStatus.PAID), 2),
        "outstanding_total": round(sum(p.amount for p in outstanding), 2),
        "overdue_count": len(overdue),
        "overdue_total": round(sum(p.amount for p in overdue), 2),
        "failed_count": sum(1 for p in rows if p.status is PaymentStatus.FAILED),
        "currency": rows[0].currency if rows else "",
    }
