#!/usr/bin/env python3
"""Build the web app's demo organisation from the real engine.

The web app runs read-only in demo mode until Supabase is configured. Its
data comes from here: farms laid out around the two pilot sites, each one
estimated by carbonstack.estimate exactly as a customer's farm would be (on
the pilot sites' published climate normals, so the build needs no network),
then rolled into vintages, payments and an activity log.

    python3 scripts/build_web_demo.py          # writes web/src/lib/demo-data.json

Deterministic: same code, same file.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carbonstack.estimate import estimate                    # noqa: E402
from carbonstack.sites import NYERI, THANJAVUR, _plot         # noqa: E402

OUT = ROOT / "web" / "src" / "lib" / "demo-data.json"
TODAY = date(2026, 10, 29)
ORG = "00000000-0000-4000-8000-000000000001"


def uid(*parts: object) -> str:
    return str(uuid.UUID(hashlib.sha256("/".join(map(str, parts)).encode()).hexdigest()[:32]))


def jitter(*parts: object) -> float:
    """Stable value in [0, 1)."""
    return int(hashlib.sha256("/".join(map(str, parts)).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def at(day: date, hour: int = 10) -> str:
    return datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc).isoformat()


def ring_geojson(ring) -> dict:
    coords = [[round(x, 7), round(y, 7)] for x, y in ring]
    return {"type": "Polygon", "coordinates": [coords + [coords[0]]]}


def normals(site) -> dict:
    return {"monthly_rain_mm": list(site.climate.monthly_rain_mm),
            "mean_temp_c": site.climate.mean_temp_c,
            "temp_amplitude_c": site.climate.temp_amplitude_c,
            "label": f"{site.admin} published normals"}


RICE_VILLAGES = ["Vallam", "Budalur", "Thirukattupalli", "Sengipatti"]
RICE_FARMERS = ["Murugan K", "Selvi R", "Arumugam P", "Lakshmi S", "Karthik V", "Meena T",
                "Rajendran M", "Kavitha N", "Senthil A", "Pandian G", "Revathi B", "Elango D"]
TREE_FARMERS = ["Wanjiru M", "Kamau J", "Njeri W", "Mwangi P", "Wambui K", "Githinji S"]

MEMBERS = [
    ("00000000-0000-4000-8000-0000000000a1", "Priya Raman", "priya@demo.carbonstack.dev", "owner"),
    ("00000000-0000-4000-8000-0000000000a2", "Daniel Otieno", "daniel@demo.carbonstack.dev", "admin"),
    ("00000000-0000-4000-8000-0000000000a3", "Anjali Iyer", "anjali@demo.carbonstack.dev", "reviewer"),
    ("00000000-0000-4000-8000-0000000000a4", "Ravi Shankar", "ravi@demo.carbonstack.dev", "analyst"),
    ("00000000-0000-4000-8000-0000000000a5", "Muthu Kumar", "muthu@demo.carbonstack.dev", "field_agent"),
    ("00000000-0000-4000-8000-0000000000a6", "Grace Wairimu", "grace@demo.carbonstack.dev", "field_agent"),
]
OWNER, ADMIN, REVIEWER, ANALYST, AGENT_TN, AGENT_KE = (m[0] for m in MEMBERS)


def main() -> int:
    created = at(date(2025, 5, 2))
    org = {"id": ORG, "name": "Demo: Cauvery & Nyeri pilots", "kind": "developer",
           "country": "India", "created_by": OWNER, "created_at": created}

    projects = [
        {"id": uid("project", "rice"), "org_id": ORG, "name": "Cauvery Delta AWD",
         "pathway": "rice", "methodology": "VM0051", "registry": "Verra", "country": "India",
         "region": "Thanjavur, Tamil Nadu", "start_date": "2025-06-01",
         "crediting_period_yrs": 7, "status": "listed", "created_by": OWNER, "created_at": created},
        {"id": uid("project", "trees"), "org_id": ORG, "name": "Nyeri Shade Coffee Agroforestry",
         "pathway": "agroforestry", "methodology": "VM0047", "registry": "Verra",
         "country": "Kenya", "region": "Nyeri County", "start_date": "2025-03-20",
         "crediting_period_yrs": 30, "status": "design", "created_by": OWNER, "created_at": created},
    ]
    rice_project, tree_project = projects

    farmers, farms, estimates, practices, soil = [], [], [], [], []

    def add_farm(i: int, site, project, farmer_name: str, village: str, agent: str, pathway: str):
        dx = (i % 4) * 0.0042 + (jitter("dx", pathway, i) - 0.5) * 0.0012
        dy = (i // 4) * 0.0031 + (jitter("dy", pathway, i) - 0.5) * 0.0009
        w = 120 + jitter("w", pathway, i) * 140
        h = 90 + jitter("h", pathway, i) * 110
        ring = _plot(site.lon + dx, site.lat + dy, width_m=w, height_m=h,
                     skew=0.08 + jitter("s", pathway, i) * 0.1)
        enrolled = site.enrolled_on + timedelta(days=int(jitter("e", pathway, i) * 25))
        farmer_id = uid("farmer", pathway, i)
        documented = i not in (3, 9) if pathway == "rice" else i != 4
        farmers.append({
            "id": farmer_id, "org_id": ORG, "name": farmer_name,
            "phone": f"+{'91 9' if pathway == 'rice' else '254 7'}{int(jitter('p', pathway, i) * 1e8):08d}",
            "village": village, "district": site.admin.split(",")[0], "state": site.admin,
            "country": site.country, "external_ref": f"{'TNJ' if pathway == 'rice' else 'NYR'}-F{i + 1:03d}",
            "consent_on": enrolled.isoformat(),
            "consent_reference": f"CONSENT/{pathway.upper()}/{i + 1:03d}",
            "carbon_rights_ref": f"CRA/{pathway.upper()}/{i + 1:03d}" if documented else None,
            "carbon_rights_signed_on": enrolled.isoformat() if documented else None,
            "payout_method": "upi" if pathway == "rice" else "mobile_money",
            "payout_reference": "****" + f"{int(jitter('u', pathway, i) * 1e4):04d}",
            "created_by": agent, "created_at": at(enrolled, 9),
        })
        farm_id = uid("farm", pathway, i)
        farm = {
            "id": farm_id, "org_id": ORG, "project_id": project["id"], "farmer_id": farmer_id,
            "name": f"{farmer_name.split()[0]} — {village} {i + 1}",
            "external_ref": f"{'TNJ' if pathway == 'rice' else 'NYR'}-{i + 1:04d}",
            "boundary": ring_geojson(ring),
            "crop": site.crop, "practice": "awd" if pathway == "rice" else "shade_trees",
            "tenure": site.tenure.value if documented else "registered_lease",
            "tenure_reference": f"{site.tenure_reference}-{i + 1}" if documented else None,
            "rice_ecosystem": "irrigated_lowland" if pathway == "rice" else None,
            "water_control": ("full" if i != 7 else "irrigation_only") if pathway == "rice" else None,
            "stems_planted": None if pathway == "rice" else int(120 * 2.5),
            "species": None if pathway == "rice" else list(site.species),
            "enrolled_on": enrolled.isoformat(),
            "seasons": [{"name": s.name, "start_month": s.start_month, "start_day": s.start_day,
                         "end_month": s.end_month, "end_day": s.end_day} for s in site.seasons]
            if pathway == "rice" else [],
            "source": "gps" if i % 3 else "drawn", "status": "enrolled",
            "created_by": agent, "created_at": at(enrolled, 11), "updated_at": at(enrolled, 11),
        }
        params = ({"baseline_ch4_kg_ha_season": round(site.baseline_ch4_kg_ha_season
                                                      * (0.85 + 0.3 * jitter("b", i)), 1),
                   "awd_reduction": site.awd_reduction}
                  if pathway == "rice" else
                  {"peak_height_m": site.shade_peak_height_m, "years_to_half": site.shade_years_to_half})
        request = {"farm": {**{k: farm[k] for k in ("id", "name", "boundary", "crop", "practice",
                                                    "tenure", "tenure_reference", "rice_ecosystem",
                                                    "water_control", "species", "enrolled_on")},
                            "pathway": pathway, "seasons": farm["seasons"] or None,
                            "country": site.country, "region": site.admin,
                            "farmer_name": farmer_name, "village": village,
                            "parameters": params},
                   "climate_source": "normals", "climate_normals": normals(site)}
        result = estimate(request, today=TODAY)
        farm["area_ha"] = result["site"]["area_ha"]
        farm["centroid_lat"] = result["site"]["centroid"]["lat"]
        farm["centroid_lon"] = result["site"]["centroid"]["lon"]
        farms.append(farm)
        for v in result["vintages"]:
            if "net_t" not in v:
                continue
            estimates.append({
                "id": uid("estimate", farm_id, v["year"]), "org_id": ORG, "farm_id": farm_id,
                "year": v["year"], "methodology": result["methodology"],
                "gross_t": v["gross_t"],
                "net_t": v["net_t"], "data_quality": result["data_quality"],
                "input": request, "result": {**result, "vintages": [v]},
                "engine_version": "carbonstack@estimate-v1", "requested_by": ANALYST,
                "created_at": at(TODAY - timedelta(days=3), 8),
            })
        if pathway == "rice":
            for year in (2025, 2026):
                for s in site.seasons:
                    if year == 2026 and s.name == "Samba":
                        continue
                    start = date(year, s.start_month, s.start_day) + timedelta(days=5)
                    practices.append({
                        "id": uid("practice", farm_id, year, s.name), "org_id": ORG, "farm_id": farm_id,
                        "year": year, "season": s.name, "practice": "awd",
                        "started_on": start.isoformat(),
                        "ended_on": s.closes_in(year).isoformat(),
                        "evidence_path": None,
                        "notes": f"{2 + int(jitter('dd', farm_id, year, s.name) * 3)} dry-downs logged by field tube",
                        "recorded_by": agent, "created_at": at(start + timedelta(days=40), 15)})
        else:
            for depth, soc_base in ((0, 2.9), (30, 1.6)):
                soil.append({
                    "id": uid("soil", farm_id, depth), "org_id": ORG, "farm_id": farm_id,
                    "sampled_on": "2025-03-12", "depth_top_cm": depth, "depth_bottom_cm": depth + 30,
                    "soc_pct": round(soc_base * (0.9 + 0.2 * jitter("soc", farm_id, depth)), 3),
                    "bulk_density": round(1.05 + 0.15 * jitter("bd", farm_id, depth) + depth / 300, 3),
                    "lab": "KALRO Soil Lab, Kabete", "lab_reference": f"KAB-25-{len(soil) + 101}",
                    "recorded_by": AGENT_KE, "created_at": at(date(2025, 3, 20), 14)})

    for i, name in enumerate(RICE_FARMERS):
        add_farm(i, THANJAVUR, rice_project, name, RICE_VILLAGES[i % len(RICE_VILLAGES)], AGENT_TN, "rice")
    for i, name in enumerate(TREE_FARMERS):
        add_farm(i, NYERI, tree_project, name, "Gatugi", AGENT_KE, "agroforestry")

    # Vintages: the sum of each project's farm estimates for a year.
    vintages, events, payments = [], [], []
    plan = {(rice_project["id"], 2025): "issued", (rice_project["id"], 2026): "submitted",
            (tree_project["id"], 2025): "approved", (tree_project["id"], 2026): "draft"}
    serial = 1
    for (pid, year), status in plan.items():
        rows = [e for e in estimates if e["year"] == year
                and next(f for f in farms if f["id"] == e["farm_id"])["project_id"] == pid]
        gross = round(math.fsum(e["gross_t"] for e in rows), 4)
        net = round(math.fsum(e["net_t"] for e in rows), 4)
        issuable = int(math.floor(net))
        vid = uid("vintage", pid, year)
        v = {"id": vid, "org_id": ORG, "project_id": pid, "year": year, "gross_t": gross,
             "net_t": net, "issuable": issuable, "status": status,
             "derivation": {"farms": [{"farm_id": e["farm_id"], "estimate_id": e["id"],
                                       "farm": next(f["name"] for f in farms if f["id"] == e["farm_id"]),
                                       "net_t": e["net_t"], "gross_t": e["gross_t"],
                                       "data_quality": e["data_quality"]} for e in rows],
                            "method": "sum of farm estimates; whole credits floor the net"},
             "submitted_by": ANALYST if status != "draft" else None,
             "approved_by": REVIEWER if status in ("approved", "issued") else None,
             "serial_start": serial if status == "issued" else None,
             "serial_end": serial + issuable - 1 if status == "issued" else None,
             "created_at": at(date(year + 1 if year < 2026 else 2026, 2, 1)),
             "updated_at": at(TODAY - timedelta(days=2))}
        if status == "issued":
            serial += issuable
        vintages.append(v)
        flow = {"draft": [], "submitted": [("draft", "submitted", ANALYST, None)],
                "approved": [("draft", "submitted", ANALYST, None),
                             ("submitted", "approved", REVIEWER, "boundaries and tenure checked")],
                "issued": [("draft", "submitted", ANALYST, None),
                           ("submitted", "on_hold", REVIEWER, "two farms missing tenure documents"),
                           ("on_hold", "submitted", ANALYST, "documents attached for TNJ-0004"),
                           ("submitted", "approved", REVIEWER, "checked against field tube logs"),
                           ("approved", "issued", ADMIN, None)]}[status]
        t0 = datetime.fromisoformat(v["created_at"])
        for k, (frm, to, actor, note) in enumerate(flow):
            events.append({"id": len(events) + 1, "org_id": ORG, "vintage_id": vid,
                           "from_status": frm, "to_status": to, "note": note, "actor": actor,
                           "at": (t0 + timedelta(days=6 * (k + 1))).isoformat()})
        if status == "issued":
            # Farmers' share: 60% of $18/credit, split by each farm's net.
            total = math.fsum(e["net_t"] for e in rows) or 1
            for k, e in enumerate(rows):
                farm = next(f for f in farms if f["id"] == e["farm_id"])
                credits = issuable * e["net_t"] / total
                if credits <= 0:
                    continue
                payments.append({
                    "id": uid("payment", vid, farm["farmer_id"]), "org_id": ORG, "vintage_id": vid,
                    "farmer_id": farm["farmer_id"], "credits": round(credits, 4),
                    "amount": round(credits * 18 * 0.6, 2), "currency": "USD",
                    "status": "paid" if k % 3 else "approved",
                    "due_on": "2026-08-15", "paid_on": "2026-08-09" if k % 3 else None,
                    "reference": f"UPI-{int(jitter('ref', vid, k) * 1e9):09d}" if k % 3 else None,
                    "created_at": at(date(2026, 7, 30))})

    # Which sources are switched on. No run history: the demo's estimates
    # were built offline on published normals, so claiming a live fetch here
    # would be inventing one.
    integrations = [
        {"id": uid("int", p), "org_id": ORG, "provider": p, "enabled": on, "config": {},
         "last_sync_at": None, "last_status": None, "created_at": created}
        for p, on in [("open-meteo", True), ("nasa-power", True),
                      ("field-sensors", False), ("verra-registry", False)]]

    audit = []
    for f in farms:
        audit.append({"actor": f["created_by"], "action": "insert", "entity": "farms",
                      "entity_id": f["id"], "detail": {"name": f["name"]}, "at": f["created_at"]})
    for e in events:
        audit.append({"actor": e["actor"], "action": "update", "entity": "vintages",
                      "entity_id": e["vintage_id"], "detail": {"status": e["to_status"]}, "at": e["at"]})
    for p in payments:
        if p["paid_on"]:
            audit.append({"actor": ADMIN, "action": "update", "entity": "payments",
                          "entity_id": p["id"], "detail": {"status": "paid"},
                          "at": at(date.fromisoformat(p["paid_on"]), 12)})
    audit.sort(key=lambda a: a["at"], reverse=True)
    for k, a in enumerate(audit):
        a.update({"id": len(audit) - k, "org_id": ORG})

    payload = {
        "generated_by": "scripts/build_web_demo.py",
        "as_of": TODAY.isoformat(),
        "organization": org,
        "members": [{"user_id": u, "full_name": n, "email": e, "role": r, "org_id": ORG,
                     "created_at": created} for u, n, e, r in MEMBERS],
        "viewer": OWNER,
        "projects": projects, "farmers": farmers, "farms": farms, "estimates": estimates,
        "practices": practices, "soil": soil, "vintages": vintages, "vintage_events": events,
        "payments": payments, "integrations": integrations, "audit": audit,
        "invitations": [{"id": uid("invite", 1), "org_id": ORG, "email": "verifier@example.org",
                         "role": "viewer", "token": "demo", "invited_by": OWNER, "accepted_at": None,
                         "expires_at": at(TODAY + timedelta(days=10)), "created_at": at(TODAY - timedelta(days=4))}],
    }
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(farms)} farms, {len(estimates)} estimates, "
          f"{len(vintages)} vintages, {len(payments)} payments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
