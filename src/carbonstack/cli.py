"""Command line: the whole lifecycle, in the order it actually happens.

    carbonstack init                              create the database
    carbonstack enroll thanjavur                  load a pilot site
    carbonstack monitor IN-TNJ-01 --to 2026-09-11 pull and store monitoring
    carbonstack quantify IN-TNJ-01 --year 2025    run the engine, record a draft
    carbonstack queue                             what is waiting on a human
    carbonstack explain IN-TNJ-01:2025            where the number came from
    carbonstack review IN-TNJ-01:2025 --approve --actor lalit --note "clean"
    carbonstack issue IN-TNJ-01:2025 --registry "Gold Standard" --actor lalit
    carbonstack pay raise IN-TNJ-01:2025 --price 12 --share 0.55 --actor lalit
    carbonstack evidence IN-TNJ-01 --out packs/tnj
    carbonstack verify                            is the event chain intact
    carbonstack serve                             HTTP API

Every command that changes a commercial record demands --actor, because every
one of them lands in the event chain under a name.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from . import (
    evidence, ledger, methodology, payments, pipeline, scenario, serialize,
    sites, stacking,
)
from .feed import (
    FeedProvider, season_warnings, series, summarise_seasons, year_confidence,
)
from .methodology.vm0042 import EmissionFactor
from .methodology.vm0047 import PerformanceBenchmark
from .methodology.vm0051 import CommonPractice, RiceEmissionFactor
from .soil import ModelValidation, SamplingDesign, SoilCore, SoilLayer, Stratum
from .remote_sensing import SyntheticProvider
from .store import Store
from .store.repo import StoreError

DEFAULT_DB = "carbonstack.db"


def _store(args) -> Store:
    return Store(args.db, actor=getattr(args, "actor", None) or "cli")


def _require_actor(args) -> str:
    actor = getattr(args, "actor", None)
    if not actor:
        raise SystemExit(
            "--actor is required: every change to a commercial record is "
            "attributed in the event chain")
    return actor


def _site(name: str):
    key = name.lower()
    for site in sites.SITES.values():
        if key in (site.id.lower(), site.village.lower(), site.label.lower().split()[0]):
            return site
    known = ", ".join(s.village.lower() for s in sites.SITES.values())
    raise SystemExit(f"unknown site {name!r}; known: {known}")


def _feed_provider(site, end: date):
    """The pilot sites are driven by the simulated feed; real projects would
    name a real provider here and nothing downstream would change."""
    kwargs = {}
    if site.track.value == "rice":
        kwargs = {"awd_lapse_season": "Kuruvai", "awd_lapse_year": 2026}
    else:
        kwargs = {"stumping_year": 2026}
    readings = series(site, site.enrolled_on, end, **kwargs)
    confidences = {}
    if site.track.value == "rice":
        by_year: dict[int, list] = {}
        for s in summarise_seasons(readings):
            by_year.setdefault(s.year, []).append(s)
        confidences = {y: year_confidence(ss) for y, ss in by_year.items()}
    return FeedProvider(readings, season_confidence=confidences), readings


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def cmd_init(args) -> int:
    with _store(args) as store:
        from .store import SCHEMA_VERSION
        print(f"database ready at {store.path}")
        print(f"  schema version {SCHEMA_VERSION}")
        print(f"  projects       {len(store.list_projects())}")
    return 0


def cmd_enroll(args) -> int:
    site = _site(args.site)
    project = sites.as_project(site)
    # Rice goes to VM0051, the purpose-built rice methodology, not VM0042.
    # VM0042 covers rice but is an agricultural land management methodology;
    # VM0051 replaces CDM AMS-III.AU and is CORSIA eligible.
    meth = {"rice": "VM0051", "cropland": "VM0042"}.get(
        site.track.value, "VM0047")
    with _store(args) as store:
        store.save_project(project, methodology_id=meth)
        print(f"enrolled {project.id} — {project.name}")
        print(f"  {len(project.plots)} plot(s), {project.area_ha:.2f} ha, "
              f"methodology {meth}")
        issues = project.eligibility_issues()
        if issues:
            print(f"  {len(issues)} plot(s) blocked:")
            for pid, problems in issues.items():
                print(f"    {pid}: {'; '.join(problems)}")
    return 0


def cmd_import(args) -> int:
    project = serialize.load(args.project_file)
    with _store(args) as store:
        store.save_project(project, methodology_id=args.methodology)
        print(f"imported {project.id}: {len(project.plots)} plot(s), "
              f"{project.area_ha:.2f} ha")
    return 0


def cmd_monitor(args) -> int:
    with _store(args) as store:
        meta = store.project_meta(args.project_id)
        end = date.fromisoformat(args.to) if args.to else date.today()
        start = (date.fromisoformat(args.since) if args.since
                 else date.fromisoformat(meta["start_date"]))

        try:
            site = _site(args.project_id)
            provider, _ = _feed_provider(site, end)
        except SystemExit:
            provider = SyntheticProvider(planting_year=start.year)

        report = pipeline.monitor(store, args.project_id, provider,
                                  start=start, end=end,
                                  actor=getattr(args, "actor", None) or "cli")
        print(report.render())
    return 0


def cmd_quantify(args) -> int:
    with _store(args) as store:
        meta = store.project_meta(args.project_id)
        end = date(args.year, 12, 31)

        try:
            site = _site(args.project_id)
        except SystemExit:
            site = None

        if site is not None:
            provider, readings = _feed_provider(site, max(end, date.today()))
            if meta["methodology_id"] == "VM0051":
                ss = [s for s in summarise_seasons(readings) if s.year == args.year]
                if not ss:
                    raise SystemExit(f"no seasons found for {args.year}")
                baseline = sum(s.baseline_ch4_kg_ha for s in ss) / max(len(ss), 1)
                project_ch4 = sum(s.project_ch4_kg_ha for s in ss) / max(len(ss), 1)
                factor = RiceEmissionFactor(
                    baseline_ch4_kg_ha_season=baseline,
                    project_ch4_kg_ha_season=project_ch4,
                    seasons_per_year=len(ss),
                    tier=args.tier,
                    source=(f"measured from {sum(s.revisits for s in ss)} "
                            f"revisits across {len(ss)} season(s)"))
                meth = methodology.get(
                    "VM0051", factors={"awd": factor},
                    common_practice=CommonPractice(
                        jurisdiction=args.jurisdiction or site.admin,
                        awd_penetration=args.awd_penetration))
            elif meta["methodology_id"] == "VM0042":
                ss = [s for s in summarise_seasons(readings) if s.year == args.year]
                if not ss:
                    raise SystemExit(f"no seasons found for {args.year}")
                factor = EmissionFactor(
                    practice="awd",
                    t_co2e_per_ha_yr=sum(s.abatement_tco2e_ha for s in ss),
                    tier=args.tier,
                    source=f"measured from {sum(s.revisits for s in ss)} revisits")
                meth = methodology.get("VM0042", factors={"awd": factor})
            else:
                meth = methodology.get(
                    "VM0047",
                    benchmark=PerformanceBenchmark(t_co2e_per_ha_yr=args.benchmark))
        else:
            provider = SyntheticProvider(planting_year=
                                         date.fromisoformat(meta["start_date"]).year)
            meth = methodology.get(meta["methodology_id"])

        extra: list[str] = []
        if site is not None and meta["methodology_id"] == "VM0042":
            extra = season_warnings(
                [s for s in summarise_seasons(readings) if s.year == args.year])
        v = pipeline.quantify(store, args.project_id, meth, provider, args.year,
                              actor=getattr(args, "actor", None) or "cli",
                              extra_warnings=extra)
        print(f"{v.id}  {v.status.value}")
        print(f"  gross      {v.gross_t:>12,.4f} tCO2e")
        for d in v.deductions:
            print(f"  − {d['name']:<9} {-d['amount_t']:>12,.4f} tCO2e "
                  f"({d['fraction'] * 100:.0f}%)")
        print(f"  net        {v.net_t:>12,.4f} tCO2e")
        print(f"  issuable   {v.issuable_whole:>12,} whole credits "
              f"(carry {v.carry:.4f})")
        for w in v.warnings:
            print(f"  ! {w}")
    return 0


def cmd_queue(args) -> int:
    with _store(args) as store:
        waiting = [v for v in ledger.list_vintages(store, args.project_id)
                   if v.status in (ledger.VintageStatus.DRAFT,
                                   ledger.VintageStatus.UNDER_REVIEW,
                                   ledger.VintageStatus.HELD)]
        if not waiting:
            print("nothing waiting on a human")
            return 0
        print(f"{len(waiting)} vintage(s) waiting")
        for v in waiting:
            flag = "!" if v.needs_review else " "
            print(f" {flag} {v.id:<26} {v.status.value:<13} "
                  f"{v.net_t:>10,.3f} tCO2e  {v.issuable_whole:>6,} credits")
            for w in v.warnings:
                print(f"     {w}")
    return 0


def cmd_explain(args) -> int:
    from .audit import Calculation, Term

    with _store(args) as store:
        v = ledger.get_vintage(store, args.vintage_id)
        print(f"{v.id} — {v.methodology_id} — {v.status.value}")
        print("=" * 72)
        for calc in ledger.calculations(store, args.vintage_id):
            c = Calculation(name=calc["name"], result_unit=calc.get("unit", ""),
                            citations=calc.get("citations", []))
            c.terms = [Term(t["label"], t["value"], t.get("unit", ""),
                            t.get("detail", "")) for t in calc["terms"]]
            if calc.get("result") is not None:
                c.finish(calc["result"])
            print(c.render("  "))
            print()
    return 0


def cmd_review(args) -> int:
    actor = _require_actor(args)
    with _store(args) as store:
        if args.submit:
            v = ledger.submit_for_review(store, args.vintage_id,
                                         actor=actor, note=args.note)
        elif args.approve:
            v = ledger.approve(store, args.vintage_id,
                               actor=actor, note=args.note)
        elif args.hold:
            v = ledger.hold(store, args.vintage_id, actor=actor, note=args.note)
        elif args.cancel:
            v = ledger.cancel(store, args.vintage_id, actor=actor, note=args.note)
        else:
            raise SystemExit("choose one of --submit, --approve, --hold, --cancel")
        print(f"{v.id} → {v.status.value}   (by {actor})")
    return 0


def cmd_issue(args) -> int:
    actor = _require_actor(args)
    with _store(args) as store:
        iss = ledger.issue(store, args.vintage_id, registry=args.registry,
                           registry_ref=args.registry_ref, actor=actor)
        print(f"issued {iss.quantity:,} credits on {iss.registry}")
        print(f"  serials {iss.serial_start} → {iss.serial_end}")
        print(f"  buffer  {ledger.buffer_balance(store)['held_t']:,.4f} tCO2e held")
    return 0


def cmd_pay(args) -> int:
    with _store(args) as store:
        if args.pay_command == "raise":
            actor = _require_actor(args)
            terms = payments.PaymentTerms(price_per_credit=args.price,
                                          farmer_share=args.share,
                                          currency=args.currency)
            made = payments.raise_payments(store, args.vintage_id, terms,
                                           actor=actor)
            total = sum(p.amount for p in made)
            print(f"raised {len(made)} payment(s), {total:,.2f} {args.currency}")
            for p in made[:10]:
                print(f"  {p.farmer_id:<18} {p.credits:>9,.3f} cr  "
                      f"{p.amount:>10,.2f} {p.currency}  due {p.due_on}")
            if len(made) > 10:
                print(f"  … and {len(made) - 10} more")
        elif args.pay_command == "list":
            rows = payments.register(store, project_id=args.project_id)
            for p in rows:
                print(f"  {p.id}  {p.farmer_id:<18} {p.amount:>10,.2f} "
                      f"{p.currency}  {p.status.value:<9} due {p.due_on}")
            s = payments.summary(store, args.project_id)
            print(f"\n  {s['payments']} payment(s), {s['farmers']} farmer(s)")
            print(f"  paid {s['paid_total']:,.2f}  outstanding "
                  f"{s['outstanding_total']:,.2f}  overdue {s['overdue_total']:,.2f}"
                  f" ({s['overdue_count']})")
        elif args.pay_command == "mark":
            actor = _require_actor(args)
            payments.approve_payment(store, args.payment_id, actor=actor)
            p = payments.mark_paid(store, args.payment_id,
                                   reference=args.reference, actor=actor)
            print(f"{p.id} paid {p.amount:,.2f} {p.currency}  ref {p.reference}")
    return 0


def cmd_eligibility(args) -> int:
    with _store(args) as store:
        project = store.load_project(args.project_id)
        issues = project.eligibility_issues()
        lost = project.area_ha - project.creditable_area_ha()

        print(f"{project.name} ({project.id})")
        print(f"  plots enrolled          {len(project.plots):>10,}")
        print(f"  plots blocked           {len(issues):>10,}")
        print(f"  area enrolled           {project.area_ha:>10,.2f} ha")
        print(f"  area creditable         {project.creditable_area_ha():>10,.2f} ha")
        if project.area_ha:
            print(f"  area lost to paperwork  {lost:>10,.2f} ha "
                  f"({lost / project.area_ha:.1%})")

        reasons: dict[str, int] = {}
        for problems in issues.values():
            for p in problems:
                reasons[p] = reasons.get(p, 0) + 1
        if reasons:
            print("\n  blocking reasons, most common first:")
            for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
                print(f"    {count:>5,}  {reason}")
        programme = project.programme_issues()
        if programme:
            print("\n  blocking the whole project, not any one plot:")
            for problem in programme:
                print(f"    ! {problem}")

        if args.verbose:
            print()
            for plot_id, problems in sorted(issues.items()):
                print(f"    {plot_id}: {'; '.join(problems)}")
    return 0


def cmd_status(args) -> int:
    with _store(args) as store:
        h = pipeline.health(store, args.project_id)
        print(f"{args.project_id}")
        print(f"  plots                {h['plots']:>10,}")
        print(f"  area                 {h['area_ha']:>10,.2f} ha")
        print(f"  creditable           {h['creditable_ha']:>10,.2f} ha "
              f"({h['area_blocked_pct']}% blocked)")
        print(f"  observations         {h['observations']:>10,}")
        print(f"  latest observation   {h['latest_observation'] or '—':>10}")
        if h["never_monitored"]:
            print("  ! never monitored")
        elif h["monitoring_stale"]:
            print(f"  ! monitoring is {h['days_since_observation']} days stale")
        vs = ledger.list_vintages(store, args.project_id)
        if vs:
            print("  vintages")
            for v in vs:
                print(f"    {v.year}  {v.status.value:<13} {v.net_t:>10,.3f} tCO2e"
                      f"  {v.issuable_whole:>6,} credits")
        print(f"  buffer held          {ledger.buffer_balance(store, args.project_id)['held_t']:>10,.4f} tCO2e")
    return 0


LAB_COLUMNS = ("plot_id", "role", "sampled_on", "lab_reference",
               "top_cm", "bottom_cm", "soc_pct", "bulk_density_g_cm3")


def cmd_soil(args) -> int:
    with _store(args) as store:
        if args.soil_command == "ingest":
            return _soil_ingest(store, args)
        if args.soil_command == "validate":
            return _soil_validate(store, args)
        if args.soil_command == "design":
            return _soil_design(args)
        if args.soil_command == "quantify":
            return _soil_quantify(store, args)
        if args.soil_command == "status":
            return _soil_status(store, args)
    return 0


def _soil_ingest(store, args) -> int:
    """Load cores from a lab CSV, which is how core data actually arrives.

    One row per layer; rows are grouped into cores by plot, role and sampling
    date. A row the lab cannot be traced to is refused rather than stored.
    """
    import csv as _csv

    actor = _require_actor(args)
    grouped: dict[tuple, dict] = {}
    with open(args.csv_file, newline="") as fh:
        reader = _csv.DictReader(fh)
        missing = [c for c in LAB_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(
                f"lab CSV is missing column(s): {', '.join(missing)}\n"
                f"expected: {', '.join(LAB_COLUMNS)}"
                f"[,stratum][,coarse_fragment_frac]")
        for row in reader:
            key = (row["plot_id"], row["role"], row["sampled_on"])
            entry = grouped.setdefault(key, {
                "lab_reference": row["lab_reference"],
                "stratum": row.get("stratum", "") or "",
                "layers": []})
            entry["layers"].append(SoilLayer(
                top_cm=float(row["top_cm"]), bottom_cm=float(row["bottom_cm"]),
                soc_pct=float(row["soc_pct"]),
                bulk_density_g_cm3=float(row["bulk_density_g_cm3"]),
                coarse_fragment_frac=float(row.get("coarse_fragment_frac") or 0)))

    stored = 0
    for (plot_id, role, sampled_on), entry in sorted(grouped.items()):
        core = SoilCore(plot_id=plot_id, sampled_on=date.fromisoformat(sampled_on),
                        lab_reference=entry["lab_reference"],
                        stratum=entry["stratum"], layers=entry["layers"])
        store.add_soil_core(args.project_id, core, role=role, actor=actor)
        stored += 1
        print(f"  {role:<10} {plot_id:<16} {sampled_on}  "
              f"{core.max_depth_cm:>5.0f} cm  "
              f"{core.soc_t_ha(30.0):>7.2f} t C/ha (0-30)")
        for problem in core.issues:
            print(f"    ! {problem}")
    print(f"\n{stored} core(s) stored from {args.csv_file}")
    return 0


def _soil_validate(store, args) -> int:
    """Record a VMD0053 model validation from a measured,modelled CSV."""
    import csv as _csv

    actor = _require_actor(args)
    pairs = []
    with open(args.csv_file, newline="") as fh:
        for row in _csv.DictReader(fh):
            pairs.append((float(row["measured_t_ha"]), float(row["modelled_t_ha"])))

    validation = ModelValidation(model_name=args.model, model_version=args.version,
                                 pairs=pairs, held_out=not args.training_data)
    store.add_model_validation(args.project_id, validation, actor=actor)
    print(validation.report().render("  "))
    print()
    problems = validation.issues()
    if problems:
        print("  NOT ACCEPTED:")
        for problem in problems:
            print(f"    ! {problem}")
        print("\n  The punitive default uncertainty will apply until a model "
              "passes.")
        return 1
    print(f"  accepted: {validation.relative_uncertainty:.1%} relative "
          f"uncertainty feeds the deduction")
    return 0


def _soil_design(args) -> int:
    strata = []
    for spec in args.strata.split(","):
        parts = spec.split(":")
        if len(parts) < 3:
            raise SystemExit(
                "each stratum is name:area_ha:soc_std_dev, comma separated")
        strata.append(Stratum(name=parts[0].strip(), area_ha=float(parts[1]),
                              soc_std_dev_t_ha=float(parts[2]),
                              existing_samples=int(parts[3]) if len(parts) > 3 else 0))

    design = SamplingDesign(strata=strata, target_margin_t_ha=args.margin,
                            confidence=args.confidence,
                            comparison_depth_cm=args.depth)
    plan = design.plan()
    print(f"sampling design over {plan['total_area_ha']:,.1f} ha")
    print(f"  precision        +/- {plan['target_margin_t_ha']} t C/ha at "
          f"{plan['confidence']:.0%} confidence")
    print(f"  cores required   {plan['total_required']:>6,}")
    print(f"  still to collect {plan['total_outstanding']:>6,}")
    print()
    print(f"  {'stratum':<28}{'area ha':>10}{'sd':>7}{'cores':>8}{'to go':>8}")
    for stratum in design.strata:
        print(f"  {stratum.name:<28}{stratum.area_ha:>10,.1f}"
              f"{stratum.soc_std_dev_t_ha:>7.1f}"
              f"{plan['required_samples'][stratum.name]:>8,}"
              f"{plan['outstanding_samples'][stratum.name]:>8,}")
    print()
    print(f"  ! {plan['depth_note']}")
    return 0


def _soil_quantify(store, args) -> int:
    project = store.load_project(args.project_id)
    baseline = store.soil_cores(args.project_id, "baseline")
    monitoring = store.soil_cores(args.project_id, "monitoring")
    if not baseline or not monitoring:
        raise SystemExit(
            f"need paired cores: {len(baseline)} baseline, "
            f"{len(monitoring)} monitoring on record")

    validation = store.latest_model_validation(args.project_id)
    result = methodology.soil_pathway(validation=validation).quantify(
        project, baseline_cores=baseline, monitoring_cores=monitoring,
        reporting_year=args.year)
    v = pipeline.record_vintage(store, result,
                                actor=getattr(args, "actor", None) or "cli")
    print(result.render())
    print(f"\n  recorded as {v.id} ({v.status.value}), "
          f"{v.issuable_whole:,} whole credit(s)")
    return 0


def _soil_status(store, args) -> int:
    baseline = store.soil_cores(args.project_id, "baseline")
    monitoring = store.soil_cores(args.project_id, "monitoring")
    project = store.load_project(args.project_id)
    paired = set(baseline) & set(monitoring)

    print(f"{args.project_id} soil")
    print(f"  plots enrolled     {len(project.plots):>6,}")
    print(f"  baseline cores     {len(baseline):>6,}")
    print(f"  monitoring cores   {len(monitoring):>6,}")
    print(f"  paired plots       {len(paired):>6,}")
    validation = store.latest_model_validation(args.project_id)
    if validation is None:
        print("  ! no accepted VMD0053 model validation; the punitive default "
              "uncertainty applies")
    else:
        print(f"  model              {validation.model_name} "
              f"{validation.model_version}, "
              f"{validation.relative_uncertainty:.1%} uncertainty")
    return 0


def cmd_stack(args) -> int:
    with _store(args) as store:
        if args.stack_command == "add":
            actor = _require_actor(args)
            geometry = None
            if args.geometry:
                geometry = [tuple(float(x) for x in pair.split(","))
                            for pair in args.geometry.split(";")]
            c = stacking.register_claim(
                store, args.project_id, args.plot_id,
                pillar=stacking.Pillar(args.pillar),
                methodology_id=args.methodology, area_ha=args.area,
                geometry=geometry, actor=actor)
            print(f"{c.pillar.value} claimed on {c.plot_id} under "
                  f"{c.methodology_id}")
            print(f"  pools    {', '.join(sorted(p.value for p in c.pools))}")
            print(f"  area     {c.area_ha:,.4f} ha")
            print(f"  boundary {'own sub-plot' if c.has_own_geometry else 'whole plot'}")
        elif args.stack_command == "audit":
            report = stacking.audit(store, args.project_id)
            print(f"{args.project_id}")
            print(f"  claims           {report['claims']:>8,}")
            print(f"  plots claimed    {report['plots_with_claims']:>8,}")
            print(f"  stacked plots    {report['stacked_plots']:>8,}")
            print(f"  stacked area     {report['stacked_ha']:>8,.2f} ha "
                  f"({report['stacked_share']:.0%} of the project)")
            if report["clean"]:
                print("  no hectare is claimed twice")
            else:
                print(f"\n  {len(report['conflicts'])} conflict(s):")
                for c in report["conflicts"]:
                    print(f"    [{c['kind']}] {c['detail']}")
                return 1
    return 0


def cmd_evidence(args) -> int:
    with _store(args) as store:
        out = evidence.build(store, args.project_id, args.out)
        print(f"evidence pack → {out}")
        for f in sorted(out.iterdir()):
            print(f"  {f.name:<22} {f.stat().st_size:>9,} bytes")
    return 0


def cmd_events(args) -> int:
    with _store(args) as store:
        rows = store.events(args.subject_type, args.subject_id)
        for e in rows[-args.limit:]:
            print(f"  {e['at']}  {e['actor']:<12} {e['kind']:<24} "
                  f"{e['subject_id']}")
            if args.verbose and e["payload"]:
                print(f"      {json.dumps(e['payload'], default=str)}")
        print(f"\n  {len(rows)} event(s)")
    return 0


def cmd_verify(args) -> int:
    with _store(args) as store:
        intact, bad = store.verify_chain()
        events = store.events()
        if intact:
            print(f"event chain intact — {len(events):,} event(s)")
            print(f"  head {events[-1]['hash'] if events else '—'}")
            return 0
        print(f"EVENT CHAIN BROKEN at event {bad}", file=sys.stderr)
        print("  a row was changed outside the application", file=sys.stderr)
        return 1


def cmd_serve(args) -> int:
    from .api import serve
    store = Store(args.db, actor="api")
    serve(store, args.host, args.port)
    return 0


# ---------------------------------------------------------------------------
# Stateless helpers, kept from the library
# ---------------------------------------------------------------------------

def cmd_methodologies(args) -> int:
    for mid in methodology.available():
        m = methodology.get(mid)
        print(f"  {m.id:<10} {m.name}")
    return 0


def cmd_sites(args) -> int:
    for site in sites.SITES.values():
        print(f"  {site.id:<12} {site.label}")
        print(f"    {site.admin}, {site.country}  {site.lat:.4f},{site.lon:.4f}")
        print(f"    {site.area_ha:.2f} ha · {site.crop}")
        print(f"    {site.intervention}")
    return 0


def cmd_demo(args) -> int:
    estate = scenario.demo_estate()
    bridge = scenario.demo_bridge()
    for project, mid, years in ((bridge, "VM0042", [2026, 2028]),
                                (estate, "VM0047", [2028, 2031])):
        planting = min(e.enrolled_on.year for e in project.enrollments)
        provider = SyntheticProvider(planting_year=planting)
        meth = methodology.get(mid)
        print()
        print(f"{project.name}  ({project.track.value})")
        print(f"  {project.area_ha:,.0f} ha enrolled, "
              f"{project.creditable_area_ha():,.0f} ha creditable, "
              f"{len(project.eligibility_issues())} plot(s) blocked")
        for year in years:
            print()
            print(meth.quantify(project, provider, year).render())
    print("\nSynthetic monitoring: this proves the pipeline, not the landscape.")
    return 0


def cmd_export(args) -> int:
    project = getattr(scenario, f"demo_{args.which}")()
    serialize.save(project, args.out)
    print(f"wrote {args.out}  ({len(project.plots)} plots, {project.area_ha:,.1f} ha)")
    return 0


# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="carbonstack",
        description="dMRV and issuance for land-based carbon projects.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--db", default=DEFAULT_DB, help=f"database file (default {DEFAULT_DB})")
    ap.add_argument("--actor", default="", help="who is doing this; required for writes")
    sub = ap.add_subparsers(dest="command", required=True)

    # Attached to every write command so --actor reads naturally after the
    # subcommand, which is where people actually type it.
    actor_opt = argparse.ArgumentParser(add_help=False)
    actor_opt.add_argument("--actor", default=None,
                           help="who is doing this; recorded in the event chain")

    sub.add_parser("init", help="create or upgrade the database").set_defaults(func=cmd_init)
    sub.add_parser("methodologies", help="list methodologies").set_defaults(func=cmd_methodologies)
    sub.add_parser("sites", help="list the built-in pilot sites").set_defaults(func=cmd_sites)
    sub.add_parser("demo", help="run both tracks with no database").set_defaults(func=cmd_demo)
    sub.add_parser("verify", help="check the event chain").set_defaults(func=cmd_verify)

    p = sub.add_parser("enroll", help="load a built-in pilot site", parents=[actor_opt])
    p.add_argument("site")
    p.set_defaults(func=cmd_enroll)

    p = sub.add_parser("import", help="load a project from JSON", parents=[actor_opt])
    p.add_argument("project_file")
    p.add_argument("--methodology", default="VM0047")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("monitor", help="pull monitoring and store it", parents=[actor_opt])
    p.add_argument("project_id")
    p.add_argument("--since")
    p.add_argument("--to")
    p.set_defaults(func=cmd_monitor)

    p = sub.add_parser("quantify", help="run the engine and record a draft vintage", parents=[actor_opt])
    p.add_argument("project_id")
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--tier", type=int, default=1, choices=[1, 2, 3],
                   help="emission factor tier for practice-based methodologies")
    p.add_argument("--benchmark", type=float, default=0.6,
                   help="performance benchmark, tCO2e/ha/yr, for ARR")
    p.add_argument("--awd-penetration", type=float, default=0.04,
                   help="share of rice area already on AWD in the jurisdiction; "
                        "VM0051 ties additionality to it")
    p.add_argument("--jurisdiction", default="",
                   help="jurisdiction the common-practice figure applies to")
    p.set_defaults(func=cmd_quantify)

    p = sub.add_parser("queue", help="vintages waiting on a human")
    p.add_argument("project_id", nargs="?")
    p.set_defaults(func=cmd_queue)

    p = sub.add_parser("explain", help="the full derivation of a vintage")
    p.add_argument("vintage_id")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("review", help="move a vintage through review", parents=[actor_opt])
    p.add_argument("vintage_id")
    p.add_argument("--submit", action="store_true")
    p.add_argument("--approve", action="store_true")
    p.add_argument("--hold", action="store_true")
    p.add_argument("--cancel", action="store_true")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("issue", help="allocate serials for an approved vintage", parents=[actor_opt])
    p.add_argument("vintage_id")
    p.add_argument("--registry", required=True)
    p.add_argument("--registry-ref", default="")
    p.set_defaults(func=cmd_issue)

    p = sub.add_parser("pay", help="farmer payments", parents=[actor_opt])
    psub = p.add_subparsers(dest="pay_command", required=True)
    q = psub.add_parser("raise", parents=[actor_opt],
                        help="create the payment register for a vintage")
    q.add_argument("vintage_id")
    q.add_argument("--price", type=float, required=True)
    q.add_argument("--share", type=float, required=True)
    q.add_argument("--currency", default="USD")
    r = psub.add_parser("list", help="show the register")
    r.add_argument("project_id", nargs="?")
    t = psub.add_parser("mark", parents=[actor_opt],
                        help="approve and mark a payment paid")
    t.add_argument("payment_id")
    t.add_argument("--reference", required=True)
    p.set_defaults(func=cmd_pay)

    p = sub.add_parser("eligibility", help="what would block issuance today")
    p.add_argument("project_id")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_eligibility)

    p = sub.add_parser("status", help="is this project healthy")
    p.add_argument("project_id")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("soil", parents=[actor_opt],
                       help="soil carbon: cores, VMD0053 validation, quantify")
    tsub = p.add_subparsers(dest="soil_command", required=True)
    q = tsub.add_parser("ingest", parents=[actor_opt], help="load cores from a lab CSV")
    q.add_argument("project_id")
    q.add_argument("csv_file")
    q = tsub.add_parser("validate", parents=[actor_opt],
                        help="record a VMD0053 model validation")
    q.add_argument("project_id")
    q.add_argument("csv_file", help="CSV of measured_t_ha,modelled_t_ha")
    q.add_argument("--model", required=True)
    q.add_argument("--version", required=True)
    q.add_argument("--training-data", action="store_true",
                   help="scored on training data; recorded but never accepted")
    q = tsub.add_parser("design", help="how many cores, and where")
    q.add_argument("--strata", required=True,
                   help="name:area_ha:soc_std_dev[:existing], comma separated")
    q.add_argument("--margin", type=float, default=2.0)
    q.add_argument("--confidence", type=float, default=0.90)
    q.add_argument("--depth", type=float, default=30.0)
    q = tsub.add_parser("quantify", parents=[actor_opt],
                        help="credit the measured SOC change")
    q.add_argument("project_id")
    q.add_argument("--year", type=int, required=True)
    q = tsub.add_parser("status", help="cores held and model state")
    q.add_argument("project_id")
    p.set_defaults(func=cmd_soil)

    p = sub.add_parser("stack", parents=[actor_opt],
                       help="pillar claims and double-counting control")
    ssub = p.add_subparsers(dest="stack_command", required=True)
    q = ssub.add_parser("add", parents=[actor_opt], help="claim a pillar on a plot")
    q.add_argument("project_id")
    q.add_argument("plot_id")
    q.add_argument("--pillar", required=True,
                   choices=[x.value for x in stacking.Pillar])
    q.add_argument("--methodology", required=True)
    q.add_argument("--area", type=float, required=True)
    q.add_argument("--geometry", default="",
                   help="sub-plot boundary as 'lon,lat;lon,lat;...'")
    r = ssub.add_parser("audit", help="is any hectare claimed twice")
    r.add_argument("project_id")
    p.set_defaults(func=cmd_stack)

    p = sub.add_parser("evidence", help="build the verification pack")
    p.add_argument("project_id")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("events", help="read the event log")
    p.add_argument("--subject-type")
    p.add_argument("--subject-id")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_events)

    p = sub.add_parser("serve", help="run the HTTP API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("export", help="write a demo project to JSON")
    p.add_argument("which", choices=["estate", "bridge"])
    p.add_argument("--out", default="project.json")
    p.set_defaults(func=cmd_export)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except StoreError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
