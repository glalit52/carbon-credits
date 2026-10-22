"""Command line for the integrations: outside data, soil projection, field
sensors, registry reconciliation and the standards comparison.

    carbonstack data climate vallam --source open-meteo --from 2015-01-01 --to 2024-12-31
    carbonstack data soil vallam
    carbonstack data imagery vallam --sensor s1 --from 2025-06-10 --to 2025-09-25
    carbonstack soc project gatugi --clay 45 --soc 55 --practice cover_crop
    carbonstack sensors ingest loggers.csv
    carbonstack sensors validate vallam loggers.csv --to 2026-09-30
    carbonstack registry reconcile export.csv --registry Verra --project IN-TNJ-01
    carbonstack standards compare --pathway rice --gross 1200 --uncertainty 0.22 --country India
    carbonstack standards list --pathway arr

Every network command takes --replay DIR (serve pinned responses, no network)
and --record DIR (pin what a live run fetched), so a number printed here can
be rebuilt later by someone without our network or our keys.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import ledger, sites, standards
from .connectors import ConnectorUnavailable, default_transport
from .connectors import registry as registry_conn
from .connectors import sensors, soilgrids, stac, weather
from .rothc import PRACTICES, Management, project_soc


def _site(name: str):
    from .cli import _site as find
    return find(name)


def _transport(args):
    return default_transport(getattr(args, "replay", None), getattr(args, "record", None))


def _emit(args, obj) -> bool:
    if getattr(args, "json", False):
        print(json.dumps(obj, indent=2, default=str))
        return True
    return False


def _climate(site, args) -> weather.ClimateSeries:
    src = getattr(args, "source", "normals")
    if src == "normals":
        c = site.climate
        return weather.from_normals(site.lat, site.lon, c.monthly_rain_mm, c.mean_temp_c,
                                    c.temp_amplitude_c, label=f"{site.id} published normals")
    start = date.fromisoformat(args.start) if args.start else date(date.today().year - 10, 1, 1)
    end = date.fromisoformat(args.end) if args.end else date(date.today().year - 1, 12, 31)
    if src == "open-meteo":
        return weather.open_meteo(_transport(args), site.lat, site.lon, start, end)
    return weather.nasa_power(_transport(args), site.lat, site.lon, start.year, end.year)


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

def cmd_data(args) -> int:
    site = _site(args.site)
    try:
        if args.data_command == "climate":
            series = _climate(site, args)
            if _emit(args, series.to_dict()):
                return 0
            print(f"{site.id} monthly climate -- {series.source}")
            if series.is_climatology:
                print("  climatology, not observed weather: fine for a forecast, "
                      "not for a hindcast")
            print(f"  {'month':<9}{'temp C':>8}{'rain mm':>9}{'ET mm':>8}  method")
            for m in (series.normals() if not series.is_climatology else series.months):
                print(f"  {m.month:<9}{m.temp_c:>8.1f}{m.rain_mm:>9.0f}{m.pet_mm:>8.0f}"
                      f"  {m.pet_method}")
            for p in series.provenance:
                print(f"  source: {p['url']} sha256:{p['sha256'][:16]}"
                      f"{' (replayed)' if p['replayed'] else ''}")
            return 0

        if args.data_command == "soil":
            prior = soilgrids.soilgrids(_transport(args), site.lat, site.lon)
            if _emit(args, prior.to_dict()):
                return 0
            lo_hi = prior.soc_interval_t_ha()
            print(f"{site.id} SoilGrids 2.0 prior, 0-{prior.depth_cm:.0f} cm")
            print(f"  clay              {prior.clay_pct:>8.1f} %")
            print(f"  SOC stock         {prior.soc_t_ha():>8.1f} t C/ha")
            if lo_hi:
                print(f"  90% interval      {lo_hi[0]:>8.1f} to {lo_hi[1]:.1f} t C/ha")
            print("  ! a 250 m modelled prior: use it to stratify and to start a "
                  "model, never as a crediting baseline")
            return 0

        if args.data_command == "imagery":
            start = date.fromisoformat(args.start)
            end = date.fromisoformat(args.end)
            cov = stac.search(_transport(args), bbox=stac.bbox_of(site.boundary, 0.001),
                              start=start, end=end, sensor=args.sensor,
                              catalogue=args.catalogue, max_cloud=args.max_cloud)
            if _emit(args, cov.to_dict()):
                return 0
            print(f"{site.id} {cov.collection}, {start} to {end}")
            print(f"  scenes              {len(cov.scenes):>6}")
            print(f"  acquisition days    {len(cov.acquisition_days):>6}")
            print(f"  usable days         {len(cov.usable_days):>6}"
                  + (f"   (scene cloud <= {cov.max_cloud:.0f}%)" if cov.max_cloud else ""))
            med = cov.median_revisit_days
            print(f"  median revisit      {med if med is not None else '-':>6} days")
            print(f"  longest gap         {cov.max_gap_days:>6} days")
            print(f"  platforms           {', '.join(cov.platforms) or '-'}")
            if args.sensor == "s1" and not cov.can_resolve(14):
                print("  ! a two-week AWD dry-down can fall entirely between two "
                      "looks in this window")
            return 0
    except ConnectorUnavailable as exc:
        raise SystemExit(f"unavailable: {exc}")
    return 0


# ---------------------------------------------------------------------------
# soc
# ---------------------------------------------------------------------------

def _flooded_months(site) -> tuple[bool, ...]:
    if site.track.value != "rice":
        return tuple([False] * 12)
    return tuple(any(s.contains(date(2025, m, 15)) for s in site.seasons)
                 for m in range(1, 13))


def cmd_soc(args) -> int:
    site = _site(args.site)
    try:
        climate = _climate(site, args)
        clay, soc0 = args.clay, args.soc
        if clay is None or soc0 is None:
            if not args.soilgrids:
                raise SystemExit("give --clay and --soc from cores, or --soilgrids to "
                                 "start from the modelled prior")
            prior = soilgrids.soilgrids(_transport(args), site.lat, site.lon)
            clay = prior.clay_pct if clay is None else clay
            soc0 = prior.soc_t_ha() if soc0 is None else soc0
    except ConnectorUnavailable as exc:
        raise SystemExit(f"unavailable: {exc}")

    baseline = Management("baseline", flooded=_flooded_months(site))
    result = project_soc(climate, clay_pct=clay, initial_soc_t_c_ha=soc0,
                         baseline=baseline, practices=args.practice or [],
                         start_year=args.start_year, horizon=args.horizon,
                         fallow_months=tuple(args.fallow or ()), draws=args.draws)
    if _emit(args, result.to_dict()):
        return 0
    print(f"{site.id} RothC-26.3 projection, {', '.join(args.practice or []) or 'no change'}")
    print(f"  climate: {result.climate_source}")
    print(f"  {'year':<7}{'baseline':>10}{'project':>10}{'change':>9}{'90% interval':>18}")
    for i, y in enumerate(result.years):
        if i % max(1, result.horizon // 10) and i != result.horizon - 1:
            continue
        print(f"  {y:<7}{result.baseline_t_c_ha[i]:>10.2f}{result.project_t_c_ha[i]:>10.2f}"
              f"{result.delta_t_c_ha[i]:>9.2f}"
              f"{result.delta_p05[i]:>9.2f} to {result.delta_p95[i]:.2f}")
    print()
    print(result.calculation.render("  "))
    for w in result.warnings:
        print(f"  ! {w}")
    print("  ! ex-ante only: crediting under VM0042 needs measured cores and a "
          "VMD0053-validated model")
    return 0


# ---------------------------------------------------------------------------
# sensors
# ---------------------------------------------------------------------------

def _read_loggers(path: str) -> list[sensors.Reading]:
    text = Path(path).read_text()
    return sensors.parse_json(text) if path.endswith(".json") else sensors.parse_csv(text)


def cmd_sensors(args) -> int:
    records = sensors.clean(_read_loggers(args.file))
    if args.sensors_command == "ingest":
        if _emit(args, [r.to_dict() for r in records]):
            return 0
        print(f"{'device':<12}{'plot':<16}{'days':>6}{'clear':>7}{'gaps':>6}"
              f"{'spikes':>8}{'AWD events':>12}")
        for r in records:
            print(f"{r.device_id:<12}{r.plot_id:<16}{len(r.days):>6}{len(r.truth()):>7}"
                  f"{len(r.gap_days):>6}{r.dropped_spikes:>8}{len(r.dry_downs()):>12}")
            for i in r.issues:
                print(f"  ! {i}")
        return 0

    from .cli import RICE_LAPSE
    from .feed import sar_series
    from .sar import WaterRegimeDetector

    site = _site(args.site)
    plot_id = f"{site.id}-P1"
    mine = [r for r in records if r.plot_id == plot_id]
    if not mine:
        raise SystemExit(f"no logger records for {plot_id}")
    end = date.fromisoformat(args.to) if args.to else date.today()
    passes = sar_series(site, site.enrolled_on, end, **RICE_LAPSE)
    calls = WaterRegimeDetector().classify(passes)
    v = sensors.validate_detector(calls, mine)
    if _emit(args, v.to_dict()):
        return 0
    r = v.result
    print(f"{site.id} detector validated against {len(mine)} logger(s)")
    print(f"  matched passes          {v.matched_passes:>6}")
    print(f"  abstained               {r['abstained']:>6}")
    print(f"  accuracy                {r['accuracy']:>6.1%}")
    print(f"  called dry when flooded {r['false_negative']:>6}   the error that over-credits")
    print(f"  called flooded when dry {r['false_positive']:>6}")
    if not v.sufficient:
        print("  ! fewer than 30 matched passes: one wrong call moves accuracy by "
              "more than the claim being tested")
    return 0


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def cmd_registry(args) -> int:
    from .cli import _store

    overrides = dict(kv.split("=", 1) for kv in (args.map or []))
    try:
        export = registry_conn.parse_export(Path(args.file).read_text(),
                                            registry=args.registry, overrides=overrides)
    except ValueError as exc:
        raise SystemExit(f"cannot read export: {exc}")
    with _store(args) as store:
        ours = [i for i in ledger.issuances(store, args.project)
                if not args.registry or i.registry.lower() == args.registry.lower()
                or not i.registry]
    rec = registry_conn.reconcile(ours, export)
    if _emit(args, rec.to_dict() | {"columns": export.columns}):
        return 0 if rec.clean else 1
    print(f"{args.registry} export: {len(export.rows)} row(s)")
    for fld, col in export.columns.items():
        print(f"  {fld:<10} <- {col!r}")
    print(f"  matched {len(rec.matches)}, retired {rec.retired_t:g} t, "
          f"cancelled {rec.cancelled_t:g} t")
    for f in rec.findings():
        print(f"  ! {f}")
    print("  reconciled clean" if rec.clean else "  NOT reconciled")
    return 0 if rec.clean else 1


# ---------------------------------------------------------------------------
# standards
# ---------------------------------------------------------------------------

def cmd_standards(args) -> int:
    if args.standards_command == "list":
        routes = (standards.routes_for(args.pathway) if args.pathway
                  else list(standards.ROUTES.values()))
        if _emit(args, [{"id": r.id, "standard": r.standard, "methodology": r.methodology,
                         "pathway": r.pathway.value, "version": str(r.version),
                         "buffer": str(r.buffer), "ccp": str(r.ccp),
                         "corsia": str(r.corsia),
                         "durability": str(r.durability) if r.durability else None,
                         "notes": list(r.notes)} for r in routes]):
            return 0
        for r in routes:
            print(f"  {r.id:<24}{r.standard:<14}{r.pathway.value:<12}{r.methodology}")
            print(f"  {'':<24}version {r.version}")
            print(f"  {'':<24}buffer {r.buffer} . CCP {r.ccp} . CORSIA {r.corsia}")
            if r.durability:
                print(f"  {'':<24}durability {r.durability}")
            for n in r.notes:
                print(f"  {'':<24}- {n}")
        return 0

    nprt = None
    if args.nprt:
        i, e, n = (float(x) for x in args.nprt.split(","))
        nprt = standards.NprtScore(i, e, n)
    cmp = standards.compare(
        args.pathway, gross_t=args.gross, relative_uncertainty=args.uncertainty,
        vintage=args.vintage, country=args.country or "", nprt=nprt,
        paris_aligned=args.paris_aligned, wants_corsia=args.corsia,
        price_point={"low": 0, "mid": 1, "high": 2}[args.price],
        biochar_h_corg=args.h_corg, biochar_random_reflectance=args.ro)
    if _emit(args, cmp.to_dict()):
        return 0
    print(cmp.render())
    return 0


# ---------------------------------------------------------------------------

def register(sub, actor_opt) -> None:
    net = __import__("argparse").ArgumentParser(add_help=False)
    net.add_argument("--replay", help="serve pinned responses from this directory")
    net.add_argument("--record", help="pin every live response into this directory")
    out = __import__("argparse").ArgumentParser(add_help=False)
    out.add_argument("--json", action="store_true", help="machine-readable output")
    clim = __import__("argparse").ArgumentParser(add_help=False)
    clim.add_argument("--source", choices=["normals", "open-meteo", "nasa-power"],
                      default="normals")
    clim.add_argument("--from", dest="start")
    clim.add_argument("--to", dest="end")

    p = sub.add_parser("data", help="outside data: climate, soil prior, imagery")
    dsub = p.add_subparsers(dest="data_command", required=True)
    q = dsub.add_parser("climate", parents=[net, out, clim], help="monthly weather")
    q.add_argument("site")
    q = dsub.add_parser("soil", parents=[net, out], help="SoilGrids prior")
    q.add_argument("site")
    q = dsub.add_parser("imagery", parents=[net, out],
                        help="Sentinel scenes available over the plot")
    q.add_argument("site")
    q.add_argument("--sensor", choices=["s1", "s2"], default="s1")
    q.add_argument("--from", dest="start", required=True)
    q.add_argument("--to", dest="end", required=True)
    q.add_argument("--catalogue", default="earth-search",
                   help="earth-search, cdse, or a STAC /search URL")
    q.add_argument("--max-cloud", type=float)
    p.set_defaults(func=cmd_data)

    p = sub.add_parser("soc", help="RothC soil carbon projection")
    ssub = p.add_subparsers(dest="soc_command", required=True)
    q = ssub.add_parser("project", parents=[net, out, clim],
                        help="baseline vs practice change, with an interval")
    q.add_argument("site")
    q.add_argument("--practice", action="append", choices=sorted(PRACTICES))
    q.add_argument("--clay", type=float, help="clay %% from cores")
    q.add_argument("--soc", type=float, help="initial SOC, t C/ha, 0-30 cm")
    q.add_argument("--soilgrids", action="store_true",
                   help="fill missing clay/SOC from the SoilGrids prior")
    q.add_argument("--fallow", type=int, action="append",
                   help="month number left bare in the baseline (repeatable)")
    q.add_argument("--start-year", type=int, default=date.today().year)
    q.add_argument("--horizon", type=int, default=20)
    q.add_argument("--draws", type=int, default=200)
    p.set_defaults(func=cmd_soc)

    p = sub.add_parser("sensors", help="field water-level loggers")
    tsub = p.add_subparsers(dest="sensors_command", required=True)
    q = tsub.add_parser("ingest", parents=[out], help="clean and summarise a logger file")
    q.add_argument("file")
    q = tsub.add_parser("validate", parents=[out],
                        help="score the SAR detector against loggers")
    q.add_argument("site")
    q.add_argument("file")
    q.add_argument("--to")
    p.set_defaults(func=cmd_sensors)

    p = sub.add_parser("registry", help="reconcile against a registry export")
    rsub = p.add_subparsers(dest="registry_command", required=True)
    q = rsub.add_parser("reconcile", parents=[out])
    q.add_argument("file", help="CSV exported from the registry")
    q.add_argument("--registry", required=True)
    q.add_argument("--project")
    q.add_argument("--map", action="append", metavar="FIELD=HEADER",
                   help="map a field to an exact column header")
    p.set_defaults(func=cmd_registry)

    p = sub.add_parser("standards", help="registries and methodologies, side by side")
    stsub = p.add_subparsers(dest="standards_command", required=True)
    q = stsub.add_parser("list", parents=[out])
    q.add_argument("--pathway", choices=[x.value for x in standards.Pathway])
    q = stsub.add_parser("compare", parents=[out])
    q.add_argument("--pathway", required=True, choices=[x.value for x in standards.Pathway])
    q.add_argument("--gross", type=float, required=True, help="gross tCO2e")
    q.add_argument("--uncertainty", type=float, required=True,
                   help="relative uncertainty, 90%% CI half-width over mean")
    q.add_argument("--vintage", type=int, default=date.today().year)
    q.add_argument("--country")
    q.add_argument("--nprt", help="internal,external,natural scores from the NPRT calculator")
    q.add_argument("--paris-aligned", action="store_true")
    q.add_argument("--corsia", action="store_true", help="only CORSIA-eligible routes")
    q.add_argument("--price", choices=["low", "mid", "high"], default="mid")
    q.add_argument("--h-corg", type=float, help="biochar molar H/Corg")
    q.add_argument("--ro", action="store_true", help="random reflectance measured")
    p.set_defaults(func=cmd_standards)
