"""Article 6 authorisation, corresponding adjustments, and the CCTS boundary.

The question this module answers is not "how many tonnes" but **"who is
allowed to count them"**, and getting it wrong does not show up as a bad
number. It shows up as a buyer telling their regulator something that is not
true.

Three claims are commonly conflated, and only one of them needs a
corresponding adjustment:

  **Unadjusted voluntary.** No authorisation, no adjustment. The host country
  still counts the tonne toward its own NDC. A buyer may say they *financed*
  the reduction; they may **not** say it offsets their own target, because the
  same tonne is already being counted by India.

  **Authorised ITMO.** The host country has issued a letter of authorisation
  and commits to a corresponding adjustment -- adding the transferred tonnes
  back to its own emissions account so it can no longer count them. Only now
  may a buyer claim the tonne against a target, and only now is it CORSIA
  eligible.

  **CCTS domestic.** An Indian Carbon Credit Certificate. It lives inside
  India's own scheme. Exporting the same tonnes internationally without an
  authorisation and an adjustment is double claiming.

What the code refuses is the gap between an authorisation and an actual
adjustment. A letter promising a corresponding adjustment is not an
adjustment; until the host country has applied and reported it, credits sold
as offsets are exposed, and this module says so rather than trusting the
letter.

None of this is legal advice, and the authorisation shapes vary by bilateral
agreement. What is encoded here is the accounting logic that every Article 6.2
arrangement shares.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .store.repo import Store, StoreError, _canonical, _d, _now, _s, new_id


class ClaimBasis(str, Enum):
    """What a buyer of this credit may truthfully say."""

    UNADJUSTED_VOLUNTARY = "unadjusted_voluntary"
    AUTHORISED_ITMO = "authorised_itmo"
    CCTS_DOMESTIC = "ccts_domestic"

    @property
    def permits_offsetting_claim(self) -> bool:
        """May the buyer count this against their own target?

        Only an adjusted ITMO. Everything else leaves the tonne in someone
        else's account, and counting it twice is the thing Article 6 exists
        to prevent.
        """
        return self is ClaimBasis.AUTHORISED_ITMO

    @property
    def unadjusted_language(self) -> str:
        """What may be said when no adjustment stands behind the tonnes."""
        return {
            ClaimBasis.UNADJUSTED_VOLUNTARY: (
                "financed emission reductions in India; may NOT be counted "
                "against the buyer's own target, as India still counts these "
                "tonnes toward its NDC"),
            ClaimBasis.AUTHORISED_ITMO: (
                "authorised for transfer, but NO corresponding adjustment has "
                "been applied yet; until it is, these tonnes may NOT be "
                "counted against the buyer's own target"),
            ClaimBasis.CCTS_DOMESTIC: (
                "Indian Carbon Credit Certificate for use within the CCTS; not "
                "for international transfer"),
        }[self]


class AuthorisedUse(str, Enum):
    """What the host country authorised the tonnes for."""

    OTHER_PARTY_NDC = "other_party_ndc"
    CORSIA = "corsia"
    OTHER_INTERNATIONAL = "other_international_mitigation_purposes"


@dataclass
class Authorisation:
    """A host country's letter of authorisation under Article 6.2.

    `corresponding_adjustment_committed` is the field that matters. An
    authorisation that does not commit to one authorises a transfer without
    fixing the double-claiming problem, and a credit sold on that basis cannot
    honestly be called an offset.
    """

    id: str
    project_id: str
    authority: str                       # e.g. "MoEFCC, Government of India"
    reference: str                       # the letter number
    issued_on: date
    authorised_use: AuthorisedUse
    authorised_volume_t: float
    corresponding_adjustment_committed: bool
    first_vintage: int
    last_vintage: int
    valid_until: date | None = None
    revoked_on: date | None = None

    def covers(self, vintage_year: int) -> bool:
        return self.first_vintage <= vintage_year <= self.last_vintage

    def is_live(self, on: date | None = None) -> bool:
        when = on or date.today()
        if self.revoked_on and self.revoked_on <= when:
            return False
        if self.valid_until and self.valid_until < when:
            return False
        return True

    def issues(self, on: date | None = None) -> list[str]:
        problems: list[str] = []
        if not self.reference.strip():
            problems.append("authorisation has no letter reference")
        if not self.authority.strip():
            problems.append("authorisation names no issuing authority")
        if self.authorised_volume_t <= 0:
            problems.append("authorisation covers no volume")
        if self.last_vintage < self.first_vintage:
            problems.append("authorisation vintage range runs backwards")
        if self.revoked_on:
            problems.append(f"authorisation was revoked on {self.revoked_on}")
        elif self.valid_until and self.valid_until < (on or date.today()):
            problems.append(f"authorisation expired on {self.valid_until}")
        if not self.corresponding_adjustment_committed:
            problems.append(
                "authorisation does not commit to a corresponding adjustment; "
                "credits under it cannot be sold as offsets against a buyer's "
                "target")
        if (self.authorised_use is AuthorisedUse.CORSIA
                and not self.corresponding_adjustment_committed):
            problems.append(
                "CORSIA use requires a corresponding adjustment")
        return problems

    def to_dict(self) -> dict:
        return {
            "id": self.id, "project_id": self.project_id,
            "authority": self.authority, "reference": self.reference,
            "issued_on": _s(self.issued_on),
            "authorised_use": self.authorised_use.value,
            "authorised_volume_t": round(self.authorised_volume_t, 4),
            "corresponding_adjustment_committed":
                self.corresponding_adjustment_committed,
            "first_vintage": self.first_vintage, "last_vintage": self.last_vintage,
            "valid_until": _s(self.valid_until), "revoked_on": _s(self.revoked_on),
            "live": self.is_live(), "issues": self.issues(),
        }


@dataclass
class CorrespondingAdjustment:
    """The host country actually adding the tonnes back to its own account.

    Distinct from the authorisation on purpose. A letter is a promise; this is
    the promise kept, and the gap between them is where double claiming
    actually lives.
    """

    id: str
    authorisation_id: str
    project_id: str
    vintage_year: int
    volume_t: float
    applied_on: date
    reported_in: str        # e.g. the host's biennial transparency report

    def issues(self) -> list[str]:
        problems: list[str] = []
        if self.volume_t <= 0:
            problems.append("adjustment covers no volume")
        if not self.reported_in.strip():
            problems.append(
                "adjustment is not tied to a transparency report; an "
                "unreported adjustment cannot be verified by a buyer")
        return problems

    def to_dict(self) -> dict:
        return {
            "id": self.id, "authorisation_id": self.authorisation_id,
            "project_id": self.project_id, "vintage_year": self.vintage_year,
            "volume_t": round(self.volume_t, 4),
            "applied_on": _s(self.applied_on), "reported_in": self.reported_in,
        }


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

@dataclass
class ClaimStatus:
    """What may be claimed for one vintage, and why."""

    project_id: str
    vintage_year: int
    issued_t: float
    basis: ClaimBasis
    adjusted_t: float
    authorisation: Authorisation | None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def unadjusted_t(self) -> float:
        """Issued tonnes with no corresponding adjustment behind them."""
        return max(0.0, self.issued_t - self.adjusted_t)

    @property
    def offsettable_t(self) -> float:
        """Tonnes a buyer may lawfully count against their own target."""
        return self.adjusted_t if self.basis is ClaimBasis.AUTHORISED_ITMO else 0.0

    @property
    def buyer_language(self) -> str:
        """What this vintage actually permits, not what its basis suggests.

        Derived from the adjusted volume rather than the basis alone. An
        authorisation with no adjustment behind it is still `authorised_itmo`,
        and a reader who saw only "offset against the buyer's target" would
        make a false claim -- which is the precise failure this module exists
        to prevent.
        """
        if self.offsettable_t <= 0:
            return self.basis.unadjusted_language
        if self.unadjusted_t > 0:
            return (f"{self.offsettable_t:,.2f} tCO2e may be counted against "
                    f"the buyer's own target; the remaining "
                    f"{self.unadjusted_t:,.2f} tCO2e have no corresponding "
                    f"adjustment and may only be described as financed")
        return ("offset against the buyer's target; the host country has "
                "adjusted its own account correspondingly")

    @property
    def corsia_eligible(self) -> bool:
        return (self.basis is ClaimBasis.AUTHORISED_ITMO
                and self.authorisation is not None
                and self.authorisation.authorised_use is AuthorisedUse.CORSIA
                and self.adjusted_t > 0)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id, "vintage_year": self.vintage_year,
            "issued_t": round(self.issued_t, 4),
            "adjusted_t": round(self.adjusted_t, 4),
            "unadjusted_t": round(self.unadjusted_t, 4),
            "offsettable_t": round(self.offsettable_t, 4),
            "basis": self.basis.value,
            "buyer_language": self.buyer_language,
            "corsia_eligible": self.corsia_eligible,
            "authorisation": self.authorisation.reference
            if self.authorisation else None,
            "reasons": list(self.reasons), "warnings": list(self.warnings),
        }


def classify(*, project_id: str, vintage_year: int, issued_t: float,
             authorisation: Authorisation | None,
             adjustments: list[CorrespondingAdjustment],
             ccts_registered: bool = False,
             on: date | None = None) -> ClaimStatus:
    """Decide what a buyer of this vintage may truthfully say.

    The default is the conservative one: with no live authorisation carrying a
    corresponding adjustment, the tonnes stay in the host country's account
    and the buyer may only claim to have financed them.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    adjusted = sum(a.volume_t for a in adjustments
                   if a.vintage_year == vintage_year
                   and (authorisation is None or a.authorisation_id == authorisation.id))

    if authorisation is None:
        reasons.append("no host-country authorisation on record")
        basis = ClaimBasis.CCTS_DOMESTIC if ccts_registered \
            else ClaimBasis.UNADJUSTED_VOLUNTARY
        if ccts_registered:
            reasons.append("registered under India's CCTS; domestic use only")
        if adjusted > 0:
            warnings.append(
                f"{adjusted:,.2f} t of corresponding adjustment recorded with "
                f"no authorisation behind it -- investigate before relying on it")
            adjusted = 0.0
        return ClaimStatus(project_id, vintage_year, issued_t, basis, 0.0,
                           None, reasons, warnings)

    problems = authorisation.issues(on)
    live = authorisation.is_live(on)
    covers = authorisation.covers(vintage_year)

    if not covers:
        reasons.append(
            f"authorisation {authorisation.reference} covers vintages "
            f"{authorisation.first_vintage}-{authorisation.last_vintage}, "
            f"not {vintage_year}")
    if not live:
        reasons.append(f"authorisation {authorisation.reference} is not live")
    if not authorisation.corresponding_adjustment_committed:
        reasons.append(
            "authorisation does not commit to a corresponding adjustment")

    if not (covers and live and authorisation.corresponding_adjustment_committed):
        warnings.extend(problems)
        basis = ClaimBasis.CCTS_DOMESTIC if ccts_registered \
            else ClaimBasis.UNADJUSTED_VOLUNTARY
        return ClaimStatus(project_id, vintage_year, issued_t, basis, 0.0,
                           authorisation, reasons, warnings)

    # Authorised and committed. Only the adjusted portion is offsettable: a
    # promise is not an adjustment.
    if adjusted <= 0:
        warnings.append(
            f"authorisation {authorisation.reference} commits to a "
            f"corresponding adjustment but none has been applied for "
            f"{vintage_year}; until it is, no tonne here may be sold as an "
            f"offset")
    elif adjusted < issued_t:
        warnings.append(
            f"{issued_t - adjusted:,.2f} t of {issued_t:,.2f} t issued have no "
            f"corresponding adjustment yet; only {adjusted:,.2f} t may be sold "
            f"as offsets")

    if adjusted > authorisation.authorised_volume_t:
        warnings.append(
            f"corresponding adjustments total {adjusted:,.2f} t against an "
            f"authorised volume of {authorisation.authorised_volume_t:,.2f} t")

    if ccts_registered:
        warnings.append(
            "vintage is registered under India's CCTS and also authorised for "
            "international transfer; confirm the CCTS certificates are "
            "cancelled or never issued for these tonnes")

    reasons.append(
        f"authorised by {authorisation.authority} under "
        f"{authorisation.reference} for {authorisation.authorised_use.value}")
    return ClaimStatus(project_id, vintage_year, issued_t,
                       ClaimBasis.AUTHORISED_ITMO, min(adjusted, issued_t),
                       authorisation, reasons, warnings)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _auth_row(r) -> Authorisation:
    return Authorisation(
        id=r["id"], project_id=r["project_id"], authority=r["authority"],
        reference=r["reference"], issued_on=_d(r["issued_on"]),
        authorised_use=AuthorisedUse(r["authorised_use"]),
        authorised_volume_t=r["authorised_volume_t"],
        corresponding_adjustment_committed=bool(r["ca_committed"]),
        first_vintage=r["first_vintage"], last_vintage=r["last_vintage"],
        valid_until=_d(r["valid_until"]), revoked_on=_d(r["revoked_on"]))


def _adj_row(r) -> CorrespondingAdjustment:
    return CorrespondingAdjustment(
        id=r["id"], authorisation_id=r["authorisation_id"],
        project_id=r["project_id"], vintage_year=r["vintage_year"],
        volume_t=r["volume_t"], applied_on=_d(r["applied_on"]),
        reported_in=r["reported_in"])


def record_authorisation(store: Store, project_id: str, *, authority: str,
                         reference: str, issued_on: date,
                         authorised_use: AuthorisedUse,
                         authorised_volume_t: float,
                         corresponding_adjustment_committed: bool,
                         first_vintage: int, last_vintage: int,
                         valid_until: date | None = None,
                         actor: str | None = None) -> Authorisation:
    auth = Authorisation(
        id=new_id("auth"), project_id=project_id, authority=authority,
        reference=reference, issued_on=issued_on,
        authorised_use=authorised_use, authorised_volume_t=authorised_volume_t,
        corresponding_adjustment_committed=corresponding_adjustment_committed,
        first_vintage=first_vintage, last_vintage=last_vintage,
        valid_until=valid_until)

    blocking = [p for p in auth.issues()
                if "reference" in p or "authority" in p or "no volume" in p
                or "backwards" in p]
    if blocking:
        raise StoreError(f"authorisation refused: {blocking[0]}")

    with store.tx() as conn:
        conn.execute(
            "INSERT INTO authorisations (id, project_id, authority, reference,"
            " issued_on, authorised_use, authorised_volume_t, ca_committed,"
            " first_vintage, last_vintage, valid_until, revoked_on, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (auth.id, project_id, authority, reference, _s(issued_on),
             authorised_use.value, authorised_volume_t,
             int(corresponding_adjustment_committed), first_vintage,
             last_vintage, _s(valid_until), None, _now()))
        store.record("article6.authorised", "project", project_id, {
            "reference": reference, "authority": authority,
            "use": authorised_use.value, "volume_t": authorised_volume_t,
            "vintages": f"{first_vintage}-{last_vintage}",
            "ca_committed": corresponding_adjustment_committed,
        }, actor=actor)
    return auth


def record_adjustment(store: Store, authorisation_id: str, *,
                      vintage_year: int, volume_t: float, applied_on: date,
                      reported_in: str, actor: str | None = None
                      ) -> CorrespondingAdjustment:
    """Record that the host country has actually made the adjustment."""
    row = store.conn.execute(
        "SELECT * FROM authorisations WHERE id = ?", (authorisation_id,)).fetchone()
    if row is None:
        raise StoreError(f"no authorisation {authorisation_id!r}")
    auth = _auth_row(row)

    if not auth.covers(vintage_year):
        raise StoreError(
            f"authorisation {auth.reference} covers vintages "
            f"{auth.first_vintage}-{auth.last_vintage}, not {vintage_year}")

    adj = CorrespondingAdjustment(
        id=new_id("ca"), authorisation_id=authorisation_id,
        project_id=auth.project_id, vintage_year=vintage_year,
        volume_t=volume_t, applied_on=applied_on, reported_in=reported_in)
    problems = adj.issues()
    if problems:
        raise StoreError(f"adjustment refused: {problems[0]}")

    with store.tx() as conn:
        conn.execute(
            "INSERT INTO corresponding_adjustments (id, authorisation_id,"
            " project_id, vintage_year, volume_t, applied_on, reported_in,"
            " created_at) VALUES (?,?,?,?,?,?,?,?)",
            (adj.id, authorisation_id, auth.project_id, vintage_year, volume_t,
             _s(applied_on), reported_in, _now()))
        store.record("article6.adjustment_applied", "project", auth.project_id, {
            "authorisation": auth.reference, "vintage": vintage_year,
            "volume_t": volume_t, "reported_in": reported_in,
        }, actor=actor)
    return adj


def revoke_authorisation(store: Store, authorisation_id: str, *, on: date,
                         reason: str, actor: str | None = None) -> None:
    """A host country can withdraw an authorisation, and buyers need to know."""
    row = store.conn.execute(
        "SELECT * FROM authorisations WHERE id = ?", (authorisation_id,)).fetchone()
    if row is None:
        raise StoreError(f"no authorisation {authorisation_id!r}")
    if row["revoked_on"]:
        raise StoreError("authorisation was already revoked")

    with store.tx() as conn:
        conn.execute("UPDATE authorisations SET revoked_on = ? WHERE id = ?",
                     (_s(on), authorisation_id))
        store.record("article6.revoked", "project", row["project_id"], {
            "reference": row["reference"], "on": _s(on), "reason": reason,
        }, actor=actor)


def authorisations(store: Store, project_id: str) -> list[Authorisation]:
    return [_auth_row(r) for r in store.conn.execute(
        "SELECT * FROM authorisations WHERE project_id = ? ORDER BY issued_on",
        (project_id,))]


def adjustments(store: Store, project_id: str) -> list[CorrespondingAdjustment]:
    return [_adj_row(r) for r in store.conn.execute(
        "SELECT * FROM corresponding_adjustments WHERE project_id = ?"
        " ORDER BY vintage_year", (project_id,))]


def claim_register(store: Store, project_id: str, *,
                   ccts_registered: bool = False,
                   on: date | None = None) -> dict:
    """What may be claimed for every issued vintage of a project.

    This is the page a buyer's counsel reads before signing, and the one an
    airline's CORSIA auditor asks for. It reports the unadjusted tonnes rather
    than quietly netting them off, because those are the ones that cannot be
    sold as offsets.
    """
    from . import ledger

    # Every authorisation, not only the live ones. A revoked authorisation
    # reported as "none on record" tells a buyer nothing about why their
    # credits stopped being offsettable, and that is the question they are
    # actually asking.
    all_auths = authorisations(store, project_id)
    adjs = adjustments(store, project_id)

    statuses: list[ClaimStatus] = []
    for vintage in ledger.list_vintages(store, project_id):
        issued = sum(i.quantity for i in ledger.issuances(store, project_id)
                     if i.vintage_id == vintage.id)
        if issued <= 0:
            continue
        covering = [a for a in all_auths if a.covers(vintage.year)]
        auth = next((a for a in covering if a.is_live(on)), None) or \
            (covering[-1] if covering else None)
        statuses.append(classify(
            project_id=project_id, vintage_year=vintage.year, issued_t=issued,
            authorisation=auth, adjustments=adjs,
            ccts_registered=ccts_registered, on=on))

    return {
        "project_id": project_id,
        "vintages": [s.to_dict() for s in statuses],
        "issued_t": round(sum(s.issued_t for s in statuses), 4),
        "offsettable_t": round(sum(s.offsettable_t for s in statuses), 4),
        "unadjusted_t": round(sum(s.unadjusted_t for s in statuses), 4),
        "corsia_eligible_t": round(
            sum(s.offsettable_t for s in statuses if s.corsia_eligible), 4),
        "authorisations": [a.to_dict() for a in authorisations(store, project_id)],
        "warnings": [w for s in statuses for w in s.warnings],
        "clean": not any(s.warnings for s in statuses),
    }
