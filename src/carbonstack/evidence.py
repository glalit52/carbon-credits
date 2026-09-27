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

from . import article6, ledger, payments, stacking
from .store.repo import Store, _canonical


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _water_regime_rows(project) -> list[dict]:
    """Classify every stored Sentinel-1 pass, from the observations alone."""
    from .sar import (
        REFERENCE_INCIDENCE_DEG, SarPass, WaterRegimeDetector,
    )

    bands: dict[tuple[str, object], dict[str, float]] = {}
    for o in project.observations:
        if o.variable not in ("vv_db", "vh_db") or o.source != "sentinel1":
            continue
        bands.setdefault((o.plot_id, o.observed_on), {})[o.variable] = o.value

    detector = WaterRegimeDetector()
    by_plot: dict[str, list[SarPass]] = {}
    for (plot_id, day), values in sorted(bands.items()):
        if "vv_db" not in values or "vh_db" not in values:
            continue
        # The stored values are already normalised to the reference
        # incidence angle, so the pass is rebuilt at that angle.
        by_plot.setdefault(plot_id, []).append(SarPass(
            day=day, vv_db=values["vv_db"], vh_db=values["vh_db"],
            incidence_deg=REFERENCE_INCIDENCE_DEG))

    rows = []
    for plot_id, passes in sorted(by_plot.items()):
        for call in detector.classify(passes):
            rows.append({
                "plot_id": plot_id,
                "day": call.day.isoformat(),
                "vv_db": round(call.vv_normalised_db, 2),
                "stage_estimate": round(call.stage_estimate, 3),
                "separation_db": round(call.separation_db, 2),
                "state": call.state.value,
                "p_flooded": round(call.p_flooded, 4),
                "confidence": round(call.confidence, 4),
                "inferred": "yes" if call.inferred else "no",
                "note": call.note,
            })
    return rows


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
    stack_report = stacking.audit(store, project_id)
    claims = article6.claim_register(store, project_id)
    inventories = store.tree_inventories(project_id)
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
            "carbon_rights_reference": (
                farmer.carbon_rights.agreement_reference
                if farmer and farmer.carbon_rights else ""),
            "carbon_rights_holder": (
                farmer.carbon_rights.holder
                if farmer and farmer.carbon_rights else ""),
            "reversal_clause_ack": (
                "yes" if farmer and farmer.carbon_rights
                and farmer.carbon_rights.reversal_clause_ack else "no"),
            "baseline_captured_on": (
                enrolment.baseline_captured_on.isoformat()
                if enrolment and enrolment.baseline_captured_on else ""),
            "practice_started_on": (
                enrolment.practice_started_on.isoformat()
                if enrolment and enrolment.practice_started_on else ""),
            "rice_ecosystem": (
                enrolment.ecosystem.value if enrolment and enrolment.ecosystem else ""),
            "water_control": (
                enrolment.water_control.value
                if enrolment and enrolment.water_control else ""),
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

    # Water regime. The rice claim rests on whether the field was dry, and
    # the only acceptable answer to "how do you know" is the radar passes it
    # was read from. Rebuilt here from the stored observations rather than
    # from the pipeline's memory: if the database cannot reproduce the call,
    # the call is not evidence.
    regime_rows = _water_regime_rows(project)
    if regime_rows:
        _write_csv(out / "water_regime.csv", regime_rows,
                   list(regime_rows[0].keys()))

    # Tree census. A census credits stems, so the register of what was
    # counted, by whom, and on which equation is the claim's evidence -- the
    # forestry equivalent of the lab reference on a soil core.
    inventory_rows = []
    for plot_id, inv in sorted(inventories.items()):
        survey = inv.survival
        stock, relative = inv.stock()
        inventory_rows.append({
            "plot_id": plot_id,
            "measured_on": inv.measured_on.isoformat(),
            "surveyed_on": survey.surveyed_on.isoformat(),
            "surveyor": survey.surveyor,
            "stems_planted": survey.stems_planted,
            "stems_sampled": survey.stems_sampled,
            "stems_alive": survey.stems_alive,
            "survival_rate": round(survey.survival_rate, 4),
            "survival_lower_bound": round(survey.survival_lower_bound(), 4),
            "stems_credited": survey.surviving_stems,
            "stems_measured": len(inv.sample),
            "species": "; ".join(sorted({m.species_key for m in inv.sample})),
            "allometry": "local fit" if inv.uses_local_allometry else "generic",
            "mean_kgco2e_per_stem": round(inv.mean_co2e_per_stem_kg, 3),
            "stock_tco2e": round(stock, 4),
            "relative_uncertainty": round(relative, 4),
            "needs_replanting": "yes" if survey.needs_replanting else "no",
        })
    _write_csv(out / "tree_inventory.csv", inventory_rows,
               list(inventory_rows[0].keys()) if inventory_rows
               else ["plot_id", "measured_on", "surveyor", "stems_planted",
                     "stems_credited", "stock_tco2e"])

    # Stacking. "Zero hectares claimed twice" is a claim a verifier wants
    # evidence for, not a promise, so the audit ships with the pack.
    (out / "stacking_audit.json").write_text(
        json.dumps(stack_report, indent=2) + "\n")

    # Article 6. A buyer's counsel and a CORSIA auditor both ask who is
    # entitled to count these tonnes, and the answer is not "we issued them".
    (out / "claim_register.json").write_text(
        json.dumps(claims, indent=2) + "\n")

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
            "methodology_version": meta["methodology_version"] or None,
            "registry": meta["registry"] or None,
            "registry_ref": meta["registry_ref"] or None,
            "crediting_period_yrs": project.crediting_period_yrs,
        },
        "governance": {
            "programme_issues": project.programme_issues(),
            "stakeholder_consultation": (
                {"held_on": project.consultation.held_on.isoformat(),
                 "record_reference": project.consultation.record_reference,
                 "participants": project.consultation.participants,
                 "grievance_channel": project.consultation.grievance_channel}
                if project.consultation else None),
            "farmers_with_carbon_rights": sum(
                1 for f in project.farmers.values() if f.carbon_rights),
            "farmers_total": len(project.farmers),
        },
        "claims": {
            "issued_t": claims["issued_t"],
            "offsettable_t": claims["offsettable_t"],
            "unadjusted_t": claims["unadjusted_t"],
            "corsia_eligible_t": claims["corsia_eligible_t"],
            "authorisations": len(claims["authorisations"]),
            "clean": claims["clean"],
        },
        "stacking": {
            "claims": stack_report["claims"],
            "stacked_plots": stack_report["stacked_plots"],
            "stacked_ha": stack_report["stacked_ha"],
            "clean": stack_report["clean"],
            "conflicts": len(stack_report["conflicts"]),
        },
        "water_regime": {
            "passes_classified": len(regime_rows),
            "flooded": sum(1 for r in regime_rows if r["state"] == "flooded"),
            "drained": sum(1 for r in regime_rows if r["state"] == "drained"),
            "not_separable": sum(1 for r in regime_rows
                                 if r["state"] == "ambiguous"),
            "carried_across_gaps": sum(1 for r in regime_rows
                                       if r["inferred"] == "yes"),
            "source": "Sentinel-1 C-band IW VV+VH, rebuilt from the stored "
                      "observations",
        } if regime_rows else None,
        "trees": {
            "plots_inventoried": len(inventories),
            "stems_planted": sum(i.survival.stems_planted
                                 for i in inventories.values()),
            "stems_credited": sum(i.survival.surviving_stems
                                  for i in inventories.values()),
            "standing_stock_tco2e": round(
                sum(i.stock()[0] for i in inventories.values()), 4),
            "plots_below_survival_floor": sum(
                1 for i in inventories.values() if i.survival.needs_replanting),
            "plots_on_generic_allometry": sum(
                1 for i in inventories.values() if not i.uses_local_allometry),
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
        f"`{p['methodology']} {p.get('methodology_version') or '(version not pinned)'}`",
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

    gov = m.get("governance", {})
    stack = m.get("stacking", {})
    lines += [
        "",
        "## Governance",
        "",
        f"- Carbon rights on file for {gov.get('farmers_with_carbon_rights', 0)} "
        f"of {gov.get('farmers_total', 0)} farmers",
    ]
    consult = gov.get("stakeholder_consultation")
    lines.append(
        f"- Stakeholder consultation {consult['held_on']}, "
        f"{consult['participants']} participants, grievance channel: "
        f"{consult['grievance_channel']}" if consult
        else "- **No stakeholder consultation on record** — required by Verra "
             "and Gold Standard")
    for problem in gov.get("programme_issues", []):
        lines.append(f"- **Blocking:** {problem}")

    lines += [
        "",
        "## Stacking",
        "",
        f"- {stack.get('claims', 0)} pillar claim(s); "
        f"{stack.get('stacked_plots', 0)} plot(s) carry more than one",
        f"- {stack.get('stacked_ha', 0):,.2f} ha stacked",
        f"- Double counting: **{'none found' if stack.get('clean') else str(stack.get('conflicts')) + ' conflict(s)'}**",
        "",
        "Methodologies partition by carbon pool, not by activity name. The "
        "audit in `stacking_audit.json` is the evidence that no pool is "
        "credited twice on the same ground.",
    ]

    cl = m.get("claims", {})
    lines += [
        "",
        "## Who may count these tonnes",
        "",
        f"- {cl.get('issued_t', 0):,.2f} tCO2e issued",
        f"- **{cl.get('offsettable_t', 0):,.2f} tCO2e** may be counted against a "
        f"buyer's own target (authorised, with a corresponding adjustment applied)",
        f"- {cl.get('unadjusted_t', 0):,.2f} tCO2e have no corresponding "
        f"adjustment and may only be described as financed, not offset",
        f"- {cl.get('corsia_eligible_t', 0):,.2f} tCO2e are CORSIA eligible",
        f"- {cl.get('authorisations', 0)} host-country authorisation(s) on record",
        "",
        "An authorisation is a promise; a corresponding adjustment is the "
        "promise kept. Only adjusted tonnes are offsettable, and "
        "`claim_register.json` shows the position vintage by vintage.",
    ]

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
