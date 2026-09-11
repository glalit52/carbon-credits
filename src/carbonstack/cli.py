"""Command line entry point.

    python -m carbonstack demo
    python -m carbonstack methodologies
    python -m carbonstack eligibility project.json
    python -m carbonstack quantify project.json --year 2030 --methodology VM0047
    python -m carbonstack explain  project.json --year 2030

`explain` prints the full derivation. It exists because the answer to "where
does this number come from" should be a command, not a meeting.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import methodology, scenario, serialize
from .domain import Project
from .remote_sensing import SyntheticProvider


def _provider(project: Project, args) -> SyntheticProvider:
    planting = min((e.enrolled_on.year for e in project.enrollments),
                   default=project.start_date.year)
    return SyntheticProvider(planting_year=planting)


def cmd_methodologies(args) -> int:
    for mid in methodology.available():
        m = methodology.get(mid)
        print(f"  {m.id:<10} {m.name}")
    return 0


def cmd_eligibility(args) -> int:
    project = serialize.load(args.project)
    issues = project.eligibility_issues()
    enrolled = {e.plot_id for e in project.enrollments}

    print(f"{project.name} ({project.id})")
    print(f"  plots enrolled        {len(enrolled):>8,}")
    print(f"  plots blocked         {len(issues):>8,}")
    print(f"  area enrolled         {project.area_ha:>8,.1f} ha")
    print(f"  area creditable       {project.creditable_area_ha():>8,.1f} ha")
    lost = project.area_ha - project.creditable_area_ha()
    if project.area_ha:
        print(f"  area lost to paperwork{lost:>8,.1f} ha "
              f"({lost / project.area_ha:.1%})")

    reasons: dict[str, int] = {}
    for problems in issues.values():
        for p in problems:
            reasons[p] = reasons.get(p, 0) + 1
    if reasons:
        print("\n  blocking reasons, most common first:")
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"    {count:>5,}  {reason}")
    if args.verbose:
        print()
        for plot_id, problems in sorted(issues.items()):
            print(f"    {plot_id}: {'; '.join(problems)}")
    return 0


def cmd_quantify(args) -> int:
    project = serialize.load(args.project)
    m = methodology.get(args.methodology)
    result = m.quantify(project, _provider(project, args), args.year)

    if args.json:
        json.dump(result.to_dict(), sys.stdout, indent=2)
        print()
    else:
        print(result.render())
    return 0


def cmd_explain(args) -> int:
    project = serialize.load(args.project)
    m = methodology.get(args.methodology)
    result = m.quantify(project, _provider(project, args), args.year)

    print(result.render())
    print()
    print("Derivation")
    print("=" * 72)
    for calc in result.calculations:
        print(calc.render("  "))
        print()
    return 0


def cmd_demo(args) -> int:
    estate = scenario.demo_estate()
    bridge = scenario.demo_bridge()
    arr = methodology.get("VM0047")
    ialm = methodology.get("VM0042")

    for project, meth, years in (
        (bridge, ialm, [2026, 2028, 2030]),
        (estate, arr, [2028, 2031, 2035]),
    ):
        provider = _provider(project, args)
        print()
        print(f"{project.name}  ({project.track.value})")
        print(f"  {project.area_ha:,.0f} ha enrolled, "
              f"{project.creditable_area_ha():,.0f} ha creditable, "
              f"{len(project.eligibility_issues())} plot(s) blocked")
        for year in years:
            print()
            print(meth.quantify(project, provider, year).render())

    print()
    print("Numbers above come from the synthetic provider and prove the "
          "pipeline, not the landscape.")
    print("Swap in a Sentinel-2 + GEDI provider and every figure becomes real.")
    return 0


def cmd_export(args) -> int:
    project = getattr(scenario, f"demo_{args.which}")()
    serialize.save(project, args.out)
    print(f"wrote {args.out}  ({len(project.plots)} plots, {project.area_ha:,.1f} ha)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="carbonstack",
        description="dMRV core for land-based carbon projects.",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("methodologies", help="list available methodologies"
                   ).set_defaults(func=cmd_methodologies)

    p = sub.add_parser("demo", help="run both tracks against synthetic monitoring")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("export", help="write a demo project to JSON")
    p.add_argument("which", choices=["estate", "bridge"])
    p.add_argument("--out", default="project.json")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("eligibility", help="what would block issuance today")
    p.add_argument("project")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_eligibility)

    for name, fn, helptext in (
        ("quantify", cmd_quantify, "credits for one vintage"),
        ("explain", cmd_explain, "credits plus the full derivation"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("project")
        p.add_argument("--year", type=int, required=True)
        p.add_argument("--methodology", default="VM0047")
        if name == "quantify":
            p.add_argument("--json", action="store_true")
        p.set_defaults(func=fn)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
