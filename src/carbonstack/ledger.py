"""The issuance ledger: what a vintage becomes once people act on it.

Quantification produces a number. This module turns that number into a
commercial record -- reviewed, approved, issued with serials, with the buffer
contribution tracked and the whole path replayable from the event chain.

Three rules here exist because breaking them is how projects get into trouble:

  **Credits are issued in whole tonnes.** Registries do not issue 1.17 credits.
  The fraction is not lost quietly -- it is recorded as a carry so the next
  vintage can use it, which is both what registries do and the difference
  between a rounding decision and a rounding bug.

  **An issued vintage is frozen.** Re-quantifying it is refused. The issued
  number is a commercial fact that somebody has bought against; a
  recomputation that disagrees is an incident to investigate, not an update to
  apply.

  **Approval and issuance are separate acts by separate people.** A pipeline
  that quantifies and issues in one step has no control at all.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from enum import Enum

from .methodology.base import VintageResult
from .store.repo import Store, StoreError, _canonical, _now, new_id


class VintageStatus(str, Enum):
    DRAFT = "draft"                 # quantified, nobody has looked
    UNDER_REVIEW = "under_review"   # in the verification queue
    APPROVED = "approved"           # cleared for issuance
    HELD = "held"                   # a reviewer stopped it
    ISSUED = "issued"               # serials allocated
    CANCELLED = "cancelled"         # withdrawn; never reaches issuance


#: Which transitions are legal. Anything not listed is refused.
TRANSITIONS: dict[VintageStatus, set[VintageStatus]] = {
    VintageStatus.DRAFT: {VintageStatus.UNDER_REVIEW, VintageStatus.CANCELLED},
    VintageStatus.UNDER_REVIEW: {VintageStatus.APPROVED, VintageStatus.HELD,
                                 VintageStatus.CANCELLED},
    VintageStatus.HELD: {VintageStatus.UNDER_REVIEW, VintageStatus.CANCELLED},
    VintageStatus.APPROVED: {VintageStatus.ISSUED, VintageStatus.HELD},
    VintageStatus.ISSUED: set(),        # terminal
    VintageStatus.CANCELLED: set(),     # terminal
}


def vintage_id(project_id: str, year: int) -> str:
    return f"{project_id}:{year}"


@dataclass
class Vintage:
    id: str
    project_id: str
    year: int
    methodology_id: str
    area_ha: float
    gross_t: float
    net_t: float
    relative_uncertainty: float
    deductions: list[dict]
    warnings: list[str]
    status: VintageStatus
    quantified_at: str

    @property
    def issuable_whole(self) -> int:
        """Whole tonnes a registry would actually issue."""
        return max(0, math.floor(self.net_t))

    @property
    def carry(self) -> float:
        """The fraction left behind, available to the next vintage."""
        return round(self.net_t - self.issuable_whole, 6)

    @property
    def buffer_t(self) -> float:
        for d in self.deductions:
            if d["name"] == "buffer pool":
                return d["amount_t"]
        return 0.0

    @property
    def needs_review(self) -> bool:
        return bool(self.warnings)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "project_id": self.project_id, "year": self.year,
            "methodology_id": self.methodology_id,
            "area_ha": round(self.area_ha, 4),
            "gross_t": round(self.gross_t, 4),
            "net_t": round(self.net_t, 4),
            "issuable_whole": self.issuable_whole,
            "carry": self.carry,
            "buffer_t": round(self.buffer_t, 4),
            "relative_uncertainty": round(self.relative_uncertainty, 4),
            "deductions": self.deductions,
            "warnings": self.warnings,
            "status": self.status.value,
            "quantified_at": self.quantified_at,
        }


def _row_to_vintage(row) -> Vintage:
    return Vintage(
        id=row["id"], project_id=row["project_id"], year=row["year"],
        methodology_id=row["methodology_id"], area_ha=row["area_ha"],
        gross_t=row["gross_t"], net_t=row["net_t"],
        relative_uncertainty=row["relative_uncertainty"],
        deductions=json.loads(row["deductions_json"]),
        warnings=json.loads(row["warnings_json"]),
        status=VintageStatus(row["status"]),
        quantified_at=row["quantified_at"],
    )


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record_vintage(store: Store, result: VintageResult, *,
                   actor: str | None = None) -> Vintage:
    """Persist a quantification as a draft vintage.

    Refuses to overwrite a vintage that has been issued. Re-quantifying one
    that is merely approved is allowed but resets it to draft, because an
    approval was given against numbers that no longer exist.
    """
    vid = vintage_id(result.project_id, result.year)
    existing = store.conn.execute(
        "SELECT * FROM vintages WHERE id = ?", (vid,)).fetchone()

    if existing is not None:
        prior = VintageStatus(existing["status"])
        if prior is VintageStatus.ISSUED:
            raise StoreError(
                f"vintage {vid} is already issued; re-quantifying it would "
                f"contradict credits that exist. Investigate as an incident.")
        if prior is VintageStatus.CANCELLED:
            raise StoreError(f"vintage {vid} was cancelled; it cannot be re-quantified")

    payload = result.to_dict()
    with store.tx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO vintages (id, project_id, year, methodology_id,"
            " area_ha, gross_t, net_t, relative_uncertainty, deductions_json,"
            " warnings_json, calculations_json, status, quantified_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vid, result.project_id, result.year, result.methodology,
             result.area_ha, result.gross_t, result.net_t,
             result.relative_uncertainty,
             _canonical(payload["deductions"]), _canonical(payload["warnings"]),
             _canonical(payload["calculations"]), VintageStatus.DRAFT.value, _now()),
        )
        store.record(
            "vintage.quantified" if existing is None else "vintage.requantified",
            "vintage", vid,
            {"gross_t": round(result.gross_t, 4), "net_t": round(result.net_t, 4),
             "area_ha": round(result.area_ha, 4),
             "warnings": len(result.warnings),
             "previous_status": existing["status"] if existing else None},
            actor=actor)
    return get_vintage(store, vid)


def get_vintage(store: Store, vid: str) -> Vintage:
    row = store.conn.execute("SELECT * FROM vintages WHERE id = ?", (vid,)).fetchone()
    if row is None:
        raise StoreError(f"no vintage {vid!r}")
    return _row_to_vintage(row)


def list_vintages(store: Store, project_id: str | None = None,
                  status: VintageStatus | None = None) -> list[Vintage]:
    sql, args = "SELECT * FROM vintages", []
    where = []
    if project_id:
        where.append("project_id = ?")
        args.append(project_id)
    if status:
        where.append("status = ?")
        args.append(status.value)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY project_id, year"
    return [_row_to_vintage(r) for r in store.conn.execute(sql, args)]


def calculations(store: Store, vid: str) -> list[dict]:
    """The full derivation kept with the vintage, for the evidence pack."""
    row = store.conn.execute(
        "SELECT calculations_json FROM vintages WHERE id = ?", (vid,)).fetchone()
    if row is None:
        raise StoreError(f"no vintage {vid!r}")
    return json.loads(row["calculations_json"])


# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------

def transition(store: Store, vid: str, to: VintageStatus, *,
               actor: str | None = None, note: str = "") -> Vintage:
    """Move a vintage, or refuse and say why."""
    v = get_vintage(store, vid)
    allowed = TRANSITIONS[v.status]
    if to not in allowed:
        allowed_text = ", ".join(sorted(s.value for s in allowed)) or "nothing"
        raise StoreError(
            f"vintage {vid} is {v.status.value}; it can move to {allowed_text}, "
            f"not {to.value}")

    if to is VintageStatus.APPROVED and v.needs_review and not note:
        raise StoreError(
            f"vintage {vid} carries {len(v.warnings)} warning(s); approving it "
            f"requires a note saying why they are acceptable")

    with store.tx() as conn:
        conn.execute("UPDATE vintages SET status = ? WHERE id = ?", (to.value, vid))
        store.record(f"vintage.{to.value}", "vintage", vid,
                     {"from": v.status.value, "note": note,
                      "warnings": v.warnings}, actor=actor)
    return get_vintage(store, vid)


def submit_for_review(store: Store, vid: str, **kw) -> Vintage:
    return transition(store, vid, VintageStatus.UNDER_REVIEW, **kw)


def approve(store: Store, vid: str, **kw) -> Vintage:
    return transition(store, vid, VintageStatus.APPROVED, **kw)


def hold(store: Store, vid: str, **kw) -> Vintage:
    return transition(store, vid, VintageStatus.HELD, **kw)


def cancel(store: Store, vid: str, **kw) -> Vintage:
    return transition(store, vid, VintageStatus.CANCELLED, **kw)


# ---------------------------------------------------------------------------
# Issuance
# ---------------------------------------------------------------------------

@dataclass
class Issuance:
    id: str
    vintage_id: str
    quantity: int
    serial_start: str
    serial_end: str
    issued_on: date
    registry: str
    registry_ref: str

    def to_dict(self) -> dict:
        return {
            "id": self.id, "vintage_id": self.vintage_id,
            "quantity": self.quantity, "serial_start": self.serial_start,
            "serial_end": self.serial_end, "issued_on": self.issued_on.isoformat(),
            "registry": self.registry, "registry_ref": self.registry_ref,
        }


def _serial(project_id: str, year: int, n: int) -> str:
    return f"{project_id}-{year}-{n:08d}"


def issue(store: Store, vid: str, *, registry: str, issued_on: date | None = None,
          registry_ref: str = "", actor: str | None = None) -> Issuance:
    """Allocate serials for an approved vintage.

    Whole tonnes only. The buffer contribution is written as its own entry so
    it can be reconciled against the registry's pool, and the sub-tonne
    remainder is recorded as a carry rather than dropped.
    """
    v = get_vintage(store, vid)
    if v.status is not VintageStatus.APPROVED:
        raise StoreError(
            f"vintage {vid} is {v.status.value}; only an approved vintage can be issued")

    quantity = v.issuable_whole
    if quantity <= 0:
        raise StoreError(
            f"vintage {vid} nets {v.net_t:.4f} tCO2e, which rounds to zero whole "
            f"credits; there is nothing to issue")

    prior = store.conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) AS n FROM issuances i"
        " JOIN vintages t ON t.id = i.vintage_id"
        " WHERE t.project_id = ? AND t.year = ?", (v.project_id, v.year)).fetchone()["n"]
    start = int(prior) + 1
    end = start + quantity - 1

    iss = Issuance(
        id=new_id("iss"), vintage_id=vid, quantity=quantity,
        serial_start=_serial(v.project_id, v.year, start),
        serial_end=_serial(v.project_id, v.year, end),
        issued_on=issued_on or date.today(), registry=registry,
        registry_ref=registry_ref,
    )

    with store.tx() as conn:
        conn.execute(
            "INSERT INTO issuances (id, vintage_id, quantity, serial_start,"
            " serial_end, issued_on, registry, registry_ref, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (iss.id, vid, quantity, iss.serial_start, iss.serial_end,
             iss.issued_on.isoformat(), registry, registry_ref, _now()))
        if v.buffer_t > 0:
            conn.execute(
                "INSERT INTO buffer_entries (id, vintage_id, quantity, reason,"
                " created_at) VALUES (?,?,?,?,?)",
                (new_id("buf"), vid, v.buffer_t,
                 "non-permanence buffer withheld at issuance", _now()))
        conn.execute("UPDATE vintages SET status = ? WHERE id = ?",
                     (VintageStatus.ISSUED.value, vid))
        store.record("vintage.issued", "vintage", vid, {
            "quantity": quantity,
            "serial_start": iss.serial_start, "serial_end": iss.serial_end,
            "registry": registry, "registry_ref": registry_ref,
            "buffer_t": round(v.buffer_t, 4), "carry": v.carry,
        }, actor=actor)
    return iss


def issuances(store: Store, project_id: str | None = None) -> list[Issuance]:
    sql = ("SELECT i.* FROM issuances i JOIN vintages v ON v.id = i.vintage_id")
    args: list = []
    if project_id:
        sql += " WHERE v.project_id = ?"
        args.append(project_id)
    sql += " ORDER BY i.issued_on, i.serial_start"
    return [
        Issuance(id=r["id"], vintage_id=r["vintage_id"], quantity=r["quantity"],
                 serial_start=r["serial_start"], serial_end=r["serial_end"],
                 issued_on=date.fromisoformat(r["issued_on"]),
                 registry=r["registry"], registry_ref=r["registry_ref"])
        for r in store.conn.execute(sql, args)
    ]


def buffer_balance(store: Store, project_id: str | None = None) -> dict:
    """What is sitting in the buffer pool, and what has been released."""
    sql = ("SELECT b.* FROM buffer_entries b JOIN vintages v ON v.id = b.vintage_id")
    args: list = []
    if project_id:
        sql += " WHERE v.project_id = ?"
        args.append(project_id)
    rows = list(store.conn.execute(sql, args))
    held = sum(r["quantity"] for r in rows if r["released_at"] is None)
    released = sum(r["quantity"] for r in rows if r["released_at"] is not None)
    return {"held_t": round(held, 4), "released_t": round(released, 4),
            "entries": len(rows)}


def release_buffer(store: Store, entry_id: str, *, note: str,
                   actor: str | None = None) -> None:
    """Release a buffer entry, e.g. when a registry closes a crediting period."""
    row = store.conn.execute(
        "SELECT * FROM buffer_entries WHERE id = ?", (entry_id,)).fetchone()
    if row is None:
        raise StoreError(f"no buffer entry {entry_id!r}")
    if row["released_at"] is not None:
        raise StoreError(f"buffer entry {entry_id} was already released")
    with store.tx() as conn:
        conn.execute(
            "UPDATE buffer_entries SET released_at = ?, release_note = ? WHERE id = ?",
            (_now(), note, entry_id))
        store.record("buffer.released", "vintage", row["vintage_id"],
                     {"entry": entry_id, "quantity": row["quantity"], "note": note},
                     actor=actor)
