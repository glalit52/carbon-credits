#!/usr/bin/env python3
"""Build the dashboard's dataset.

Runs the monitoring feed and the quantification engine over both pilot sites
and writes one JSON document the dashboard reads. The series runs past today
on the real satellite revisit cadence, and the dashboard reveals only the
passes that have actually happened -- so opening it next week genuinely shows
readings that were not visible this week.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "model"))

from carbonstack import methodology                       # noqa: E402
from carbonstack.biomass import co2e_per_ha                # noqa: E402
from carbonstack.domain import TrackKind                   # noqa: E402
from carbonstack.feed import (                             # noqa: E402
    CH4_GWP100, FeedProvider, REVISIT_DAYS, series, summarise_seasons,
    year_confidence,
)
from carbonstack.methodology.vm0042 import EmissionFactor  # noqa: E402
from carbonstack.methodology.vm0047 import PerformanceBenchmark  # noqa: E402
from carbonstack.sites import NYERI, THANJAVUR, as_project  # noqa: E402

SERIES_END = date(2027, 12, 31)      # the live feed the dashboard reveals
PROJECTION_END = date(2040, 12, 31)  # long enough to show the estate reaching maturity
TODAY = date.today()

# Commercial assumptions. Sourced in docs/research/01-mitti-labs-and-varaha.md;
# every one of them is a placeholder until a term sheet says otherwise.
PRICE = {"rice": 12.0, "agroforestry": 26.0}
FARMER_SHARE = {"rice": 0.55, "agroforestry": 0.60}
MRV_COST_PER_HA_YR = {"rice": 18.0, "agroforestry": 26.0}
FIXED_PROJECT_COST_YR = 190_000.0   # validation, verification, registry, ops


def rice_block() -> dict:
    site = THANJAVUR
    project = as_project(site)
    plot = next(iter(project.plots.values()))

    readings = series(site, site.enrolled_on, SERIES_END,
                      awd_lapse_season="Kuruvai", awd_lapse_year=2026)
    seasons = summarise_seasons(readings)

    # Roll seasons up to a crediting year, weighting confidence by abatement.
    by_year: dict[int, list] = {}
    for s in seasons:
        by_year.setdefault(s.year, []).append(s)

    vintages = []
    for year, ss in sorted(by_year.items()):
        complete = [s for s in ss if s.end <= TODAY]
        abatement_per_ha = sum(s.abatement_tco2e_ha for s in ss)
        confidence = year_confidence(ss)

        # Quantify through the engine, with this year's measured abatement as
        # the emission factor so the deductions are the engine's, not ours.
        factor = EmissionFactor(
            practice="awd",
            t_co2e_per_ha_yr=abatement_per_ha,
            tier=1,
            source=(f"measured from {sum(s.revisits for s in ss)} revisits across "
                    f"{len(ss)} season(s); {CH4_GWP100}x GWP100"),
        )
        m = methodology.get("VM0042", factors={"awd": factor})
        provider = FeedProvider(readings, season_confidence={year: confidence})
        result = m.quantify(project, provider, year)

        payload = result.to_dict()
        payload["warnings"] = list(payload["warnings"])
        for s_ in ss:
            if s_.dry_down_events == 0:
                payload["warnings"].append(
                    f"{s_.season} {s_.year}: no dry-down detected across "
                    f"{s_.revisits} revisits -- the practice may not have happened")
            elif s_.adoption_confidence < 0.6:
                payload["warnings"].append(
                    f"{s_.season} {s_.year}: adoption confidence "
                    f"{s_.adoption_confidence:.0%}, only {s_.clear_revisits} of "
                    f"{s_.revisits} passes were clear")
        vintages.append({
            **payload,
            "complete": len(complete) == len(ss),
            "seasons": [s.to_dict() for s in ss],
            "abatement_tco2e_ha": round(abatement_per_ha, 4),
            "adoption_confidence": round(confidence, 3),
        })

    # Project forward on the same model, so the credit curve can be charted
    # past the live feed. Marked separately -- these are not observations.
    long_readings = series(site, site.enrolled_on, PROJECTION_END,
                           awd_lapse_season="Kuruvai", awd_lapse_year=2026)
    projection = []
    for s in summarise_seasons(long_readings):
        projection.append({"year": s.year, "season": s.season,
                           "abatement_tco2e_ha": round(s.abatement_tco2e_ha, 4),
                           "confidence": round(s.adoption_confidence, 3)})

    return {
        "site": site_meta(site, project),
        "readings": [r.to_dict() for r in readings],
        "vintages": vintages,
        "projection": projection,
        "methodology": {
            "id": "VM0042",
            "name": "Improved Agricultural Land Management / rice water management",
            "note": ("Abatement is measured from the flux series rather than "
                     "taken from a table, but the emission factor is still "
                     "Tier 1 until local flux chambers calibrate it."),
        },
    }


def coffee_block() -> dict:
    site = NYERI
    project = as_project(site)

    readings = series(site, site.enrolled_on, SERIES_END, stumping_year=2026)
    provider = FeedProvider(readings)
    m = methodology.get(
        "VM0047",
        benchmark=PerformanceBenchmark(
            t_co2e_per_ha_yr=0.6,
            source="placeholder; replace with a Verra-vetted data service provider",
            matched_control_n=0,
        ),
    )

    long_readings = series(site, site.enrolled_on, PROJECTION_END,
                           stumping_year=2026)
    long_provider = FeedProvider(long_readings)

    vintages = []
    for year in range(site.enrolled_on.year + 1, PROJECTION_END.year + 1):
        result = m.quantify(project, long_provider, year)
        payload = result.to_dict()
        payload["warnings"] = list(payload["warnings"]) + [
            f"{year}: {f}" for f in long_provider.flags_near(date(year, 12, 31))
            if "cloud" not in f
        ]
        vintages.append({
            **payload,
            "complete": date(year, 12, 31) <= TODAY,
            "observed": year <= SERIES_END.year,
        })

    # Standing stock curve, for the chart that shows why this pathway is slow.
    stock = []
    for r in readings:
        if r.canopy_height_m is None:
            continue
        value, sigma = co2e_per_ha(r.canopy_height_m,
                                   height_uncertainty_m=r.canopy_uncertainty_m or 0)
        stock.append({"day": r.day.isoformat(),
                      "tco2e_ha": round(value, 2),
                      "sigma": round(sigma, 2)})

    return {
        "site": site_meta(site, project),
        "readings": [r.to_dict() for r in readings],
        "standing_stock": stock,
        "vintages": vintages,
        "methodology": {
            "id": "VM0047",
            "name": "Afforestation, Reforestation and Revegetation (area-based)",
            "note": ("Credits are growth net of a dynamic performance "
                     "benchmark. Both the benchmark and the allometric "
                     "equation are placeholders."),
        },
    }


def site_meta(site, project) -> dict:
    return {
        "id": site.id,
        "label": site.label,
        "country": site.country,
        "admin": site.admin,
        "lat": site.lat,
        "lon": site.lon,
        "boundary": [list(v) for v in site.boundary],
        "area_ha": round(site.area_ha, 3),
        "track": site.track.value,
        "crop": site.crop,
        "intervention": site.intervention,
        "species": list(site.species),
        "tenure": site.tenure.value,
        "tenure_reference": site.tenure_reference,
        "enrolled_on": site.enrolled_on.isoformat(),
        "farmer": site.farmer_name,
        "village": site.village,
        "notes": site.notes,
        "seasons": [
            {"name": s.name, "start": f"{s.start_month:02d}-{s.start_day:02d}",
             "end": f"{s.end_month:02d}-{s.end_day:02d}"}
            for s in site.seasons
        ],
        "monthly_rain_mm": list(site.climate.monthly_rain_mm),
        "mean_temp_c": site.climate.mean_temp_c,
        "creditable_ha": round(project.creditable_area_ha(), 3),
        "eligibility_issues": project.eligibility_issues(),
        "revisit_days": REVISIT_DAYS,
    }


def economics(blocks: list[dict]) -> dict:
    """What one plot earns, and what it would take to matter.

    The dashboard leads with this, because at 2-3 ha the answer is
    discouraging and every other decision follows from it.
    """
    per_site = []
    for block in blocks:
        site = block["site"]
        track = site["track"]
        vintages = block["vintages"]

        settled = [v for v in vintages if v["complete"]]
        current = (sum(v["net_t"] for v in settled) / len(settled)) if settled else 0.0
        mature = max((v["net_t"] for v in vintages), default=0.0)

        price = PRICE[track]
        share = FARMER_SHARE[track]
        mrv_rate = MRV_COST_PER_HA_YR[track]
        mrv = site["area_ha"] * mrv_rate

        def economics_at(credits: float) -> dict:
            gross = credits * price
            farmer = gross * share
            developer = gross - farmer
            return {
                "credits": round(credits, 3),
                "gross_revenue": round(gross, 2),
                "to_farmer": round(farmer, 2),
                "to_developer": round(developer, 2),
                "net_of_mrv": round(developer - mrv, 2),
            }

        # The number the product is built against: what monitoring may cost
        # per hectare before this plot stops paying for its own supervision.
        developer_at_maturity = mature * price * (1 - share)
        breakeven_mrv = (developer_at_maturity / site["area_ha"]
                         if site["area_ha"] else 0.0)

        per_site.append({
            "site_id": site["id"],
            "label": site["label"],
            "track": track,
            "area_ha": site["area_ha"],
            "price": price,
            "farmer_share_pct": share,
            "mrv_cost_per_ha_yr": mrv_rate,
            "mrv_cost": round(mrv, 2),
            "settled": economics_at(current),
            "mature": economics_at(mature),
            "mature_year": max(vintages, key=lambda v: v["net_t"])["year"]
            if vintages else None,
            "credits_per_ha_mature": round(mature / site["area_ha"], 3)
            if site["area_ha"] else 0.0,
            "breakeven_mrv_per_ha": round(breakeven_mrv, 2),
            "mrv_headroom": round(breakeven_mrv - mrv_rate, 2),
        })

    # Aggregation: how much land it takes to carry the fixed cost of being a
    # registered project at all, once monitoring is paid for.
    scaling = []
    for s in per_site:
        margin = s["mature"]["net_of_mrv"]
        viable = margin > 0
        scaling.append({
            "site_id": s["site_id"],
            "label": s["label"],
            "margin_per_plot_mature": margin,
            "viable_at_current_mrv": viable,
            "plots_to_cover_fixed_cost": round(FIXED_PROJECT_COST_YR / margin)
            if viable else None,
            "hectares_to_cover_fixed_cost": round(
                FIXED_PROJECT_COST_YR / margin * s["area_ha"]) if viable else None,
            "required_mrv_per_ha": s["breakeven_mrv_per_ha"],
        })

    return {
        "per_site": per_site,
        "scaling": scaling,
        "fixed_project_cost_yr": FIXED_PROJECT_COST_YR,
        "mrv_cost_per_ha_yr": MRV_COST_PER_HA_YR,
        "note": ("Fixed cost is validation, verification, registry fees and "
                 "project operations for one registered project, independent "
                 "of how much land sits inside it."),
    }


def main() -> int:
    rice = rice_block()
    coffee = coffee_block()

    payload = {
        "generated_at": date.today().isoformat(),
        "series_end": SERIES_END.isoformat(),
        "provenance": {
            "locations": "real",
            "climatology": "real published monthly normals",
            "crop_calendars": "real",
            "boundaries": "drawn, not surveyed",
            "monitoring": "simulated on the real 5-day Sentinel-2 revisit cadence",
            "prices_and_costs": "placeholder, sourced in docs/research/",
        },
        "blocks": [rice, coffee],
        "economics": economics([rice, coffee]),
    }

    out = ROOT / "dashboard" / "data.json"
    out.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    readable = sum(len(b["readings"]) for b in payload["blocks"])
    print(f"wrote {out.relative_to(ROOT)}  "
          f"{out.stat().st_size / 1024:.0f} KB, {readable} readings, "
          f"{sum(len(b['vintages']) for b in payload['blocks'])} vintages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
