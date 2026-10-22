"""Reconciling our ledger against the registry's.

The registry is the system of record for a credit; our ledger is the system
of record for *why* it exists. Those two have to agree to the tonne, and the
moment they stop agreeing is the moment someone has sold, retired or
cancelled something the other side does not know about. That is found by
reconciling, routinely, not by a buyer's due diligence.

Verra, Gold Standard, Puro.earth and Isometric all publish searchable public
registries and all let a project proponent export issuances as CSV. None of
those exports share a header row, and they have changed their columns more
than once, so this module does not hard-code any of them. It matches columns
by **aliases** and reports which column it used for which field, so a changed
export fails loudly at the header rather than quietly at a quantity.

Matching is by serial block first -- the only key that cannot collide -- then
by the registry reference we recorded at issuance, and only then by vintage
and quantity, which is reported as a weaker match because two issuances of
the same size in the same year are not unusual.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date

from ..ledger import Issuance

FIELDS = {
    "serial": ("serial number", "serial numbers", "serial range", "serial block",
               "serial_number", "serials"),
    "quantity": ("quantity issued", "quantity of units", "quantity", "credits issued",
                 "volume", "issued quantity", "total vintage quantity", "units"),
    "vintage": ("vintage", "vintage year", "vintage start", "monitoring period start",
                "vintage_start"),
    "project": ("id", "project id", "gsid", "gs id", "project", "project_id",
                "project number"),
    "status": ("status", "credit status", "retirement status", "unit status"),
    "issued_on": ("issuance date", "date of issuance", "issued on", "issued_on"),
    "reference": ("issuance id", "transaction id", "batch id", "reference",
                  "registry reference", "registry_ref"),
}

REQUIRED = ("quantity", "vintage")


@dataclass
class RegistryRow:
    line: int
    project: str
    vintage: int | None
    quantity: float
    serial: str = ""
    status: str = ""
    issued_on: str = ""
    reference: str = ""


@dataclass
class RegistryExport:
    registry: str
    rows: list[RegistryRow]
    columns: dict[str, str]                 # field -> header actually used
    ignored_columns: list[str] = field(default_factory=list)


def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", h.strip().lower().replace("_", " "))


def _year(text: str) -> int | None:
    m = re.search(r"(19|20)\d{2}", text or "")
    return int(m.group(0)) if m else None


def _number(text: str) -> float:
    cleaned = re.sub(r"[^\d.\-]", "", text or "")
    if not cleaned:
        raise ValueError(f"no number in {text!r}")
    return float(cleaned)


def parse_export(text: str, *, registry: str,
                 overrides: dict[str, str] | None = None) -> RegistryExport:
    """Read a registry CSV export, mapping columns by alias.

    `overrides` maps a field to an exact header for exports whose column
    names no alias covers. An ambiguous match -- two headers that both look
    like a quantity -- is refused rather than resolved by column order.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = reader.fieldnames or []
    by_norm = {_norm(h): h for h in headers}
    columns: dict[str, str] = {}
    for fld, aliases in FIELDS.items():
        if overrides and fld in overrides:
            if overrides[fld] not in headers:
                raise ValueError(f"override for {fld!r}: no column {overrides[fld]!r}")
            columns[fld] = overrides[fld]
            continue
        hits = [by_norm[a] for a in aliases if a in by_norm]
        if len(hits) > 1 and fld == "quantity":
            # "Quantity Issued" beats "Total Vintage Quantity" when both
            # exist: the first is this issuance, the second is the vintage.
            hits = hits[:1]
        if len(set(hits)) > 1:
            raise ValueError(
                f"columns {hits} could all be {fld!r}; pass an override")
        if hits:
            columns[fld] = hits[0]
    missing = [f for f in REQUIRED if f not in columns]
    if missing:
        raise ValueError(
            f"{registry} export has no column for {missing}; headers were {headers}")

    rows = []
    for i, r in enumerate(reader, start=2):
        qty_text = (r.get(columns["quantity"]) or "").strip()
        if not qty_text:
            continue
        rows.append(RegistryRow(
            line=i,
            project=(r.get(columns.get("project", ""), "") or "").strip(),
            vintage=_year(r.get(columns["vintage"], "")),
            quantity=_number(qty_text),
            serial=(r.get(columns.get("serial", ""), "") or "").strip(),
            status=(r.get(columns.get("status", ""), "") or "").strip(),
            issued_on=(r.get(columns.get("issued_on", ""), "") or "").strip(),
            reference=(r.get(columns.get("reference", ""), "") or "").strip(),
        ))
    used = set(columns.values())
    return RegistryExport(registry, rows, columns,
                          [h for h in headers if h not in used])


@dataclass
class Match:
    issuance_id: str
    registry_line: int
    basis: str                  # "serial" | "reference" | "vintage+quantity"
    ours: float
    theirs: float

    @property
    def agrees(self) -> bool:
        return abs(self.ours - self.theirs) < 1e-6


@dataclass
class Reconciliation:
    registry: str
    matches: list[Match]
    missing_at_registry: list[Issuance]
    unknown_to_us: list[RegistryRow]
    retired_t: float
    cancelled_t: float

    @property
    def disagreements(self) -> list[Match]:
        return [m for m in self.matches if not m.agrees]

    @property
    def weak_matches(self) -> list[Match]:
        return [m for m in self.matches if m.basis == "vintage+quantity"]

    @property
    def clean(self) -> bool:
        return not (self.disagreements or self.missing_at_registry or self.unknown_to_us)

    def findings(self) -> list[str]:
        out = []
        for m in self.disagreements:
            out.append(f"{m.issuance_id}: we issued {m.ours:g}, registry line "
                       f"{m.registry_line} shows {m.theirs:g}")
        for iss in self.missing_at_registry:
            out.append(f"{iss.id} ({iss.quantity} t, {iss.serial_start}) is in our "
                       f"ledger but not in the {self.registry} export")
        for row in self.unknown_to_us:
            out.append(f"registry line {row.line}: {row.quantity:g} t vintage "
                       f"{row.vintage} has no issuance in our ledger")
        for m in self.weak_matches:
            out.append(f"{m.issuance_id} matched on vintage and quantity only; "
                       f"record the registry reference at issuance")
        return out

    def to_dict(self) -> dict:
        return {
            "registry": self.registry, "clean": self.clean,
            "matched": len(self.matches),
            "disagreements": len(self.disagreements),
            "missing_at_registry": [i.id for i in self.missing_at_registry],
            "unknown_to_us": [r.line for r in self.unknown_to_us],
            "retired_t": self.retired_t, "cancelled_t": self.cancelled_t,
            "findings": self.findings(),
        }


def _year_of_vintage(iss: Issuance) -> int:
    return int(iss.vintage_id.rsplit(":", 1)[1])


def reconcile(ours: list[Issuance], export: RegistryExport) -> Reconciliation:
    rows = list(export.rows)
    taken: set[int] = set()
    matches: list[Match] = []
    missing: list[Issuance] = []

    def claim(pred, basis, iss) -> bool:
        for row in rows:
            if row.line in taken or not pred(row):
                continue
            taken.add(row.line)
            matches.append(Match(iss.id, row.line, basis, iss.quantity, row.quantity))
            return True
        return False

    for iss in ours:
        if claim(lambda r: len(r.serial) >= 8 and (iss.serial_start in r.serial
                                                    or r.serial in iss.serial_start),
                 "serial", iss):
            continue
        if iss.registry_ref and claim(
                lambda r: iss.registry_ref in (r.reference, r.serial), "reference", iss):
            continue
        year = _year_of_vintage(iss)
        if claim(lambda r: r.vintage == year and abs(r.quantity - iss.quantity) < 1e-6,
                 "vintage+quantity", iss):
            continue
        missing.append(iss)

    def total(word: str) -> float:
        return sum(r.quantity for r in rows if word in r.status.lower())

    return Reconciliation(
        registry=export.registry, matches=matches,
        missing_at_registry=missing,
        unknown_to_us=[r for r in rows if r.line not in taken],
        retired_t=total("retire"), cancelled_t=total("cancel"),
    )
