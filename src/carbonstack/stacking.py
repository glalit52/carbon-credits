"""Stacking pillars on one hectare without double counting.

Stacking is the product's differentiator and its largest audit risk, and the
two are the same fact: the moment one hectare carries more than one claim, a
verifier's first question is whether any tonne is being sold twice.

The rule that does most of the work is not obvious. Methodologies are not
partitioned by *activity*, they are partitioned by **carbon pool**:

  * VM0051 credits avoided methane and deliberately leaves soil alone.
  * VM0042 credits soil organic carbon **and** rice methane -- both pools.
  * VM0047 credits tree biomass, above and below ground.

So a paddy hectare cannot carry VM0051 methane and a VM0042 soil claim side
by side, even though they sound like different products: VM0042 already
credits the methane, so the methane would be sold twice. The lawful shapes
are one VM0042 project covering both pools, or VM0051 for methane alone
(faster, and CORSIA eligible). Trees stack with either, because biomass is a
pool neither of the others touches -- but only on separate geometry, since a
bund planted with trees is not also growing rice.

This module refuses the unlawful shapes at registration time rather than
discovering them at verification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from .store.repo import Store, StoreError, _canonical, _now, new_id


class Pillar(str, Enum):
    METHANE = "methane"
    SOIL_CARBON = "soil_carbon"
    TREES = "trees"


class CarbonPool(str, Enum):
    """What a claim actually credits. Two claims on the same pool and the
    same ground is double counting, whatever the pillars are called."""

    CH4_AVOIDED = "ch4_avoided"
    SOIL_ORGANIC_CARBON = "soil_organic_carbon"
    ABOVE_GROUND_BIOMASS = "above_ground_biomass"
    BELOW_GROUND_BIOMASS = "below_ground_biomass"


#: Which pools each methodology credits. This table is the whole engine --
#: every conflict below is derived from it rather than hand-listed, so adding
#: a methodology means adding one row and nothing else.
METHODOLOGY_POOLS: dict[str, frozenset[CarbonPool]] = {
    "VM0051": frozenset({CarbonPool.CH4_AVOIDED}),
    "VM0042": frozenset({CarbonPool.CH4_AVOIDED, CarbonPool.SOIL_ORGANIC_CARBON}),
    "VM0047": frozenset({CarbonPool.ABOVE_GROUND_BIOMASS,
                         CarbonPool.BELOW_GROUND_BIOMASS}),
}


def pools_for(methodology_id: str) -> frozenset[CarbonPool]:
    try:
        return METHODOLOGY_POOLS[methodology_id.upper()]
    except KeyError:
        known = ", ".join(sorted(METHODOLOGY_POOLS))
        raise StoreError(
            f"unknown methodology {methodology_id!r} for stacking; known: {known}"
        ) from None


@dataclass
class PillarClaim:
    """One pillar's claim over part of a plot."""

    id: str
    project_id: str
    plot_id: str
    pillar: Pillar
    methodology_id: str
    area_ha: float
    geometry: list[tuple[float, float]] | None = None

    @property
    def pools(self) -> frozenset[CarbonPool]:
        return pools_for(self.methodology_id)

    @property
    def has_own_geometry(self) -> bool:
        """A sub-plot boundary of its own, rather than the whole plot.

        Trees on a bund occupy ground the rice does not. Without a boundary
        the two claims are over the same hectare and cannot be separated.
        """
        return bool(self.geometry)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "project_id": self.project_id,
            "plot_id": self.plot_id, "pillar": self.pillar.value,
            "methodology_id": self.methodology_id,
            "area_ha": round(self.area_ha, 4),
            "pools": sorted(p.value for p in self.pools),
            "has_own_geometry": self.has_own_geometry,
        }


@dataclass
class Conflict:
    """Why two claims cannot both stand."""

    plot_id: str
    kind: str
    detail: str
    claims: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"plot_id": self.plot_id, "kind": self.kind,
                "detail": self.detail, "claims": list(self.claims)}

    def __str__(self) -> str:
        return f"{self.plot_id}: {self.detail}"


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

def conflicts_between(a: PillarClaim, b: PillarClaim) -> list[Conflict]:
    """Every reason this pair cannot coexist."""
    found: list[Conflict] = []
    shared = a.pools & b.pools

    if shared:
        names = ", ".join(sorted(p.value for p in shared))
        found.append(Conflict(
            plot_id=a.plot_id, kind="double_counting",
            detail=(f"{a.methodology_id} ({a.pillar.value}) and "
                    f"{b.methodology_id} ({b.pillar.value}) both credit "
                    f"{names} on the same plot -- the same tonne would be sold "
                    f"twice"),
            claims=[a.id, b.id]))

    # Distinct pools still need distinct ground. Rice and the trees on its
    # bund are different pools, but they are not the same square metre.
    if not shared and not (a.has_own_geometry and b.has_own_geometry):
        found.append(Conflict(
            plot_id=a.plot_id, kind="shared_geometry",
            detail=(f"{a.pillar.value} and {b.pillar.value} stack on this plot "
                    f"but at least one has no sub-plot boundary; stacking "
                    f"requires separate geometry per activity"),
            claims=[a.id, b.id]))

    return found


def check_plot(claims: list[PillarClaim], plot_area_ha: float | None = None
               ) -> list[Conflict]:
    """All conflicts among the claims on a single plot."""
    found: list[Conflict] = []
    for i, a in enumerate(claims):
        for b in claims[i + 1:]:
            found += conflicts_between(a, b)

    if plot_area_ha is not None and len(claims) > 1:
        claimed = sum(c.area_ha for c in claims)
        if claimed > plot_area_ha * 1.001:      # tolerate float noise
            found.append(Conflict(
                plot_id=claims[0].plot_id, kind="area_overclaim",
                detail=(f"claims total {claimed:,.4f} ha on a {plot_area_ha:,.4f} "
                        f"ha plot -- {claimed - plot_area_ha:,.4f} ha claimed "
                        f"more than once"),
                claims=[c.id for c in claims]))
    return found


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _row(r) -> PillarClaim:
    return PillarClaim(
        id=r["id"], project_id=r["project_id"], plot_id=r["plot_id"],
        pillar=Pillar(r["pillar"]), methodology_id=r["methodology_id"],
        area_ha=r["area_ha"],
        geometry=([tuple(v) for v in json.loads(r["geometry_json"])]
                  if r["geometry_json"] else None))


def claims(store: Store, project_id: str | None = None,
           plot_id: str | None = None) -> list[PillarClaim]:
    sql, args, where = "SELECT * FROM pillar_claims", [], []
    if project_id:
        where.append("project_id = ?")
        args.append(project_id)
    if plot_id:
        where.append("plot_id = ?")
        args.append(plot_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY plot_id, pillar"
    return [_row(r) for r in store.conn.execute(sql, args)]


def register_claim(store: Store, project_id: str, plot_id: str, *,
                   pillar: Pillar, methodology_id: str, area_ha: float,
                   geometry: list[tuple[float, float]] | None = None,
                   actor: str | None = None) -> PillarClaim:
    """Add a pillar to a plot, or refuse and say which rule it breaks.

    Refusing here is the point. A conflict found at registration costs a
    conversation; the same conflict found at verification costs the vintage.
    """
    project = store.load_project(project_id)
    if plot_id not in project.plots:
        raise StoreError(f"plot {plot_id!r} is not in project {project_id!r}")
    plot_area = project.plots[plot_id].area_ha

    proposed = PillarClaim(
        id=new_id("clm"), project_id=project_id, plot_id=plot_id,
        pillar=pillar, methodology_id=methodology_id.upper(),
        area_ha=area_ha, geometry=geometry)
    pools_for(proposed.methodology_id)      # validates the methodology

    existing = claims(store, plot_id=plot_id)
    if any(c.pillar is pillar for c in existing):
        raise StoreError(
            f"plot {plot_id} already carries a {pillar.value} claim")

    found = check_plot(existing + [proposed], plot_area)
    if found:
        lines = "\n  ".join(str(c) for c in found)
        raise StoreError(
            f"cannot stack {pillar.value} on {plot_id}:\n  {lines}")

    with store.tx() as conn:
        conn.execute(
            "INSERT INTO pillar_claims (id, project_id, plot_id, pillar,"
            " methodology_id, carbon_pool, area_ha, geometry_json, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (proposed.id, project_id, plot_id, pillar.value,
             proposed.methodology_id,
             ",".join(sorted(p.value for p in proposed.pools)),
             area_ha,
             _canonical([list(v) for v in geometry]) if geometry else None,
             _now()))
        store.record("stacking.claim_registered", "project", project_id, {
            "plot_id": plot_id, "pillar": pillar.value,
            "methodology": proposed.methodology_id,
            "area_ha": round(area_ha, 4),
            "pools": sorted(p.value for p in proposed.pools),
            "own_geometry": proposed.has_own_geometry,
        }, actor=actor)
    return proposed


def set_geometry(store: Store, claim_id: str,
                 geometry: list[tuple[float, float]] | None, *,
                 actor: str | None = None) -> PillarClaim:
    """Give an existing claim its own sub-plot boundary.

    Needed because the first pillar on a plot is legitimately registered
    without one -- there is nothing to separate it from yet. The boundary
    becomes necessary only when a second pillar arrives, and at that point
    the first claim has to be able to acquire one without being deleted and
    re-registered, which would break its audit trail.

    The new geometry is checked against the plot's other claims before it is
    stored, so this cannot be used to sneak past a conflict.
    """
    row = store.conn.execute(
        "SELECT * FROM pillar_claims WHERE id = ?", (claim_id,)).fetchone()
    if row is None:
        raise StoreError(f"no pillar claim {claim_id!r}")

    current = _row(row)
    amended = PillarClaim(
        id=current.id, project_id=current.project_id, plot_id=current.plot_id,
        pillar=current.pillar, methodology_id=current.methodology_id,
        area_ha=current.area_ha, geometry=geometry)

    project = store.load_project(current.project_id)
    others = [c for c in claims(store, plot_id=current.plot_id)
              if c.id != claim_id]
    area = project.plots[current.plot_id].area_ha \
        if current.plot_id in project.plots else None
    found = check_plot(others + [amended], area)
    if found:
        lines = "\n  ".join(str(c) for c in found)
        raise StoreError(
            f"that boundary does not resolve the plot's claims:\n  {lines}")

    with store.tx() as conn:
        conn.execute("UPDATE pillar_claims SET geometry_json = ? WHERE id = ?",
                     (_canonical([list(v) for v in geometry]) if geometry else None,
                      claim_id))
        store.record("stacking.geometry_set", "project", current.project_id, {
            "claim": claim_id, "plot_id": current.plot_id,
            "pillar": current.pillar.value,
            "vertices": len(geometry) if geometry else 0,
        }, actor=actor)
    return amended


def audit(store: Store, project_id: str) -> dict:
    """Every stacking conflict in a project, and what is stacked where.

    Run before any issuance touching a stacked plot, and shipped in the
    evidence pack: "zero hectares claimed twice" is a claim a verifier will
    want evidence for, not a promise.
    """
    project = store.load_project(project_id)
    all_claims = claims(store, project_id=project_id)

    by_plot: dict[str, list[PillarClaim]] = {}
    for c in all_claims:
        by_plot.setdefault(c.plot_id, []).append(c)

    found: list[Conflict] = []
    for plot_id, plot_claims in sorted(by_plot.items()):
        area = project.plots[plot_id].area_ha if plot_id in project.plots else None
        found += check_plot(plot_claims, area)

    stacked = {p: cs for p, cs in by_plot.items() if len(cs) > 1}
    stacked_ha = sum(project.plots[p].area_ha for p in stacked
                     if p in project.plots)

    return {
        "project_id": project_id,
        "claims": len(all_claims),
        "plots_with_claims": len(by_plot),
        "stacked_plots": len(stacked),
        "stacked_ha": round(stacked_ha, 4),
        "stacked_share": round(
            stacked_ha / project.area_ha, 4) if project.area_ha else 0.0,
        "conflicts": [c.to_dict() for c in found],
        "clean": not found,
        "detail": {p: [c.to_dict() for c in cs] for p, cs in sorted(by_plot.items())},
    }
