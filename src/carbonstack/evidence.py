"""The evidence pack: what a verification body actually receives.

Everything upstream exists to produce this. A validation and verification body
does not want access to our dashboard; it wants a dated, self-contained bundle
it can read, check and keep -- and the faster it can satisfy itself, the
cheaper and sooner the verification.

So the pack is plain files: CSVs a verifier can open in a spreadsheet, JSON for
anything nested, a readable summary, and the event chain with its integrity
check already run. No database, no server, nothing to install.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

from . import ledger, payments
from .store.repo import Store, _canonical


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build(store: Store, project_id: str, out_dir: str | Path) -> Path:
    """Write the pack and return its directory."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    project = store.load_project(project_id)
    meta = store.project_meta(project_id)
    issues = project.eligibility_issues()
    vintages = ledger.list_vintages(store, project_id)
    issued = ledger.issuances(store, project_id)
    pay_rows = payments.register(store, project_id=project_id)
    intact, bad = store.verify_chain()

    # -- plot register -----------------------------------------------------
    plot_rows = []
    for plot in project.plots.values():
        farmer = project.farmers.get(plot.farmer_id)
        enrolment = next((e for e in project.enrollments if e.plot_id == plot.id), None)
        problems = issues.get(plot.id, [])
        plot_rows.append({
            "plot_id": plot.id,
            "farmer_id": plot.farmer_id,
            "farmer_name": farmer.name if farmer else "",
            "village": farmer.village if farmer else "",
            "district": farmer.district if farmer else "",
            "area_ha": round(plot.area_ha, 4),
            "centroid_lon": round(plot.centroid[0], 6),
            "centroid_lat": round(plot.centroid[1], 6),
            "boundary_fingerprint": plot.fingerprint,
            "tenure": plot.tenure.value,
            "tenure_reference": plot.tenure_reference,
            "consent_on": farmer.consent_on.isoformat() if farmer and farmer.consent_on else "",
            "consent_reference": farmer.consent_reference if farmer else "",
            "enrolled_on": enrolment.enrolled_on.isoformat() if enrolment else "",
            "practice": enrolment.practice if enrolment else "",
            "creditable": "no" if problems else "yes",
            "exclusion_reason": "; ".join(problems),
        })
    _write_csv(out / "plot_register.csv", plot_rows, list(plot_rows[0].keys())
               if plot_rows else ["plot_id"])

    # -- observations ------------------------------------------------------
    obs_rows = [{
        "plot_id": o.plot_id, "observed_on": o.observed_on.isoformat(),
        "variable": o.variable, "value": o.value, "unit": o.unit,
        "source": o.source, "uncertainty": o.uncertainty,
    } for o in project.observations]
    _write_csv(out / "observations.csv", obs_rows,
               ["plot_id", "observed_on", "variable", "value", "unit",
                "source", "uncertainty"])

    # -- vintages and issuance --------------------------------------------
    vintage_rows = []
    for v in vintages:
        row = {
            "vintage_id": v.id, "year": v.year, "methodology": v.methodology_id,
            "area_ha": round(v.area_ha, 4),
            "gross_tco2e": round(v.gross_t, 4),
            "net_tco2e": round(v.net_t, 4),
            "issuable_whole": v.issuable_whole,
            "carry": v.carry,
            "relative_uncertainty": round(v.relative_uncertainty, 4),
            "status": v.status.value,
            "warnings": "; ".join(v.warnings),
        }
        for d in v.deductions:
            row["deduction_" + d["name"].replace(" ", "_")] = round(d["amount_t"], 4)
        vintage_rows.append(row)
    columns = sorted({k for r in vintage_rows for k in r}) if vintage_rows else ["vintage_id"]
    ordered = [c for c in ["vintage_id", "year", "methodology", "area_ha",
                           "gross_tco2e"] if c in columns]
    ordered += [c for c in columns if c not in ordered]
    _write_csv(out / "vintages.csv", vintage_rows, ordered)

    _write_csv(out / "issuances.csv", [i.to_dict() for i in issued],
               ["id", "vintage_id", "quantity", "serial_start", "serial_end",
                "issued_on", "registry", "registry_ref"])

    # -- derivations -------------------------------------------------------
    derivations = {v.id: ledger.calculations(store, v.id) for v in vintages}
    (out / "derivations.json").write_text(json.dumps(derivations, indent=2) + "\n")

    # -- payments ----------------------------------------------------------
    _write_csv(out / "payments.csv", [p.to_dict() for p in pay_rows],
               ["id", "vintage_id", "farmer_id", "credits", "amount", "currency",
                "status", "due_on", "paid_on", "reference"])

    # -- event chain -------------------------------------------------------
    events = store.events()
    _write_csv(out / "event_log.csv", [{
        "id": e["id"], "at": e["at"], "actor": e["actor"], "kind": e["kind"],
        "subject_type": e["subject_type"], "subject_id": e["subject_id"],
        "payload": _canonical(e["payload"]), "hash": e["hash"],
        "prev_hash": e["prev_hash"],
    } for e in events],
        ["id", "at", "actor", "kind", "subject_type", "subject_id", "payload",
         "prev_hash", "hash"])

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": {
            "id": project.id, "name": project.name, "track": project.track.value,
            "country": project.country,
            "start_date": project.start_date.isoformat(),
            "methodology": meta["methodology_id"],
            "registry": meta["registry"] or None,
            "registry_ref": meta["registry_ref"] or None,
            "crediting_period_yrs": project.crediting_period_yrs,
        },
        "area": {
            "enrolled_ha": round(project.area_ha, 4),
            "creditable_ha": round(project.creditable_area_ha(), 4),
            "plots": len(project.plots),
            "plots_excluded": len(issues),
            "farmers": len(project.farmers),
        },
        "monitoring": {
            "observations": len(project.observations),
            "variables": sorted({o.variable for o in project.observations}),
            "sources": sorted({o.source for o in project.observations}),
            "first": min((o.observed_on for o in project.observations),
                         default=None).isoformat() if project.observations else None,
            "last": max((o.observed_on for o in project.observations),
                        default=None).isoformat() if project.observations else None,
        },
        "credits": {
            "vintages": len(vintages),
            "gross_tco2e": round(sum(v.gross_t for v in vintages), 4),
            "net_tco2e": round(sum(v.net_t for v in vintages), 4),
            "issued_credits": sum(i.quantity for i in issued),
            "buffer": ledger.buffer_balance(store, project_id),
        },
        "payments": payments.summary(store, project_id),
        "integrity": {
            "event_count": len(events),
            "chain_intact": intact,
            "first_bad_event": bad,
            "head_hash": events[-1]["hash"] if events else None,
        },
        "files": sorted(p.name for p in out.iterdir() if p.is_file()),
        "caveats": [
            "Allometric equation is a generic placeholder and must be replaced "
            "with a locally calibrated equation before issuance.",
            "Performance benchmark is a placeholder and must be sourced from a "
            "registry-vetted data service provider.",
            "Where the monitoring source is 'synthetic' or 'feed', values are "
            "simulated and must not be used for issuance.",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "SUMMARY.md").write_text(_summary_md(manifest, vintages, issues))

    store.record("evidence.exported", "project", project_id, {
        "files": len(manifest["files"]) + 1,
        "chain_intact": intact,
        "head_hash": manifest["integrity"]["head_hash"],
    })
    return out


def _summary_md(m: dict, vintages: list, issues: dict) -> str:
    p, a, c = m["project"], m["area"], m["credits"]
    lines = [
        f"# Evidence pack — {p['name']}",
        "",
        f"Generated {m['generated_at']} · project `{p['id']}` · methodology "
        f"`{p['methodology']}`",
        "",
        "## Project",
        "",
        f"- Track: {p['track']}, {p['country']}",
        f"- Start date: {p['start_date']}, crediting period {p['crediting_period_yrs']} years",
        f"- Registry: {p['registry'] or 'not yet listed'}"
        + (f" ({p['registry_ref']})" if p["registry_ref"] else ""),
        "",
        "## Area and eligibility",
        "",
        f"- {a['plots']:,} plots across {a['farmers']:,} farmers, "
        f"{a['enrolled_ha']:,.2f} ha enrolled",
        f"- **{a['creditable_ha']:,.2f} ha creditable**; {a['plots_excluded']:,} "
        f"plot(s) excluded",
    ]
    if issues:
        reasons: dict[str, int] = {}
        for problems in issues.values():
            for prob in problems:
                reasons[prob] = reasons.get(prob, 0) + 1
        lines.append("")
        lines.append("Exclusions, most common first:")
        lines.append("")
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {count} × {reason}")

    mo = m["monitoring"]
    lines += [
        "",
        "## Monitoring",
        "",
        f"- {mo['observations']:,} observations, {mo['first'] or '—'} to {mo['last'] or '—'}",
        f"- Variables: {', '.join(mo['variables']) or '—'}",
        f"- Sources: {', '.join(mo['sources']) or '—'}",
        "",
        "## Credits",
        "",
        f"- {c['vintages']} vintage(s): {c['gross_tco2e']:,.2f} tCO2e gross, "
        f"{c['net_tco2e']:,.2f} tCO2e net of deductions",
        f"- {c['issued_credits']:,} credits issued (whole tonnes)",
        f"- Buffer pool: {c['buffer']['held_t']:,.2f} tCO2e held across "
        f"{c['buffer']['entries']} entr(ies)",
        "",
        "| Vintage | Gross | Net | Issuable | Uncertainty | Status |",
        "|---|---|---|---|---|---|",
    ]
    for v in vintages:
        lines.append(
            f"| {v.year} | {v.gross_t:,.2f} | {v.net_t:,.2f} | {v.issuable_whole:,} | "
            f"{v.relative_uncertainty:.1%} | {v.status.value} |")

    pay = m["payments"]
    integrity = m["integrity"]
    lines += [
        "",
        "## Farmer payments",
        "",
        f"- {pay['payments']} payment(s) to {pay['farmers']} farmer(s)",
        f"- Paid {pay['paid_total']:,.2f} {pay['currency']}, "
        f"outstanding {pay['outstanding_total']:,.2f}, "
        f"overdue {pay['overdue_total']:,.2f} across {pay['overdue_count']}",
        "",
        "## Integrity",
        "",
        f"- {integrity['event_count']:,} events in the log",
        f"- Hash chain: **{'intact' if integrity['chain_intact'] else 'BROKEN at event ' + str(integrity['first_bad_event'])}**",
        f"- Head hash: `{integrity['head_hash'] or '—'}`",
        "",
        "Every event's hash covers its own content and its predecessor's hash. "
        "Recompute the chain from `event_log.csv` to confirm nothing was edited "
        "after the fact.",
        "",
        "## Caveats",
        "",
    ]
    for c_ in m["caveats"]:
        lines.append(f"- {c_}")
    lines.append("")
    return "\n".join(lines)
