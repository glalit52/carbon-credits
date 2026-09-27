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
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "model"))

from carbonstack import (                                  # noqa: E402
    evidence, forecast, ledger, methodology, payments, pipeline,
)
from carbonstack.agroforestry import (                     # noqa: E402
    CensusInventory, StemMeasurement, SurvivalSurvey,
)
from carbonstack.biomass import co2e_per_ha                # noqa: E402
from carbonstack.domain import TrackKind                   # noqa: E402
from carbonstack.feed import (                             # noqa: E402
    CH4_GWP100, FeedProvider, REVISIT_DAYS, sar_seasons, sar_series,
    sar_truth, series, summarise_seasons, year_confidence,
)
from carbonstack.sar import (                              # noqa: E402
    S1_REVISIT_DAYS, SarProvider, WaterRegimeDetector, score,
)
from carbonstack.methodology.vm0051 import (                # noqa: E402
    CommonPractice, RiceEmissionFactor,
)
from carbonstack.methodology.vm0047 import PerformanceBenchmark  # noqa: E402
from carbonstack.sites import NYERI, THANJAVUR, as_project  # noqa: E402
from carbonstack.store import Store                        # noqa: E402
from carbonstack.store.repo import StoreError              # noqa: E402

SERIES_END = date(2027, 12, 31)      # the live feed the dashboard reveals
PROJECTION_END = date(2040, 12, 31)  # long enough to show the estate reaching maturity

# The build is a snapshot as of a stated date, not "whenever this ran". Which
# vintages have settled, and therefore the economics, depend on that date -- so
# leaving it implicit makes the output drift with the calendar and there is no
# way to rebuild what was committed. CARBONSTACK_AS_OF pins it; the payload
# records it; scripts/check_dashboard_fresh.py reads it back to reproduce.
TODAY = (date.fromisoformat(os.environ["CARBONSTACK_AS_OF"])
         if os.environ.get("CARBONSTACK_AS_OF") else date.today())

# Commercial assumptions. Sourced in docs/research/01-mitti-labs-and-varaha.md;
# every one of them is a placeholder until a term sheet says otherwise.
PRICE = {"rice": 12.0, "agroforestry": 26.0}
FARMER_SHARE = {"rice": 0.55, "agroforestry": 0.60}
MRV_COST_PER_HA_YR = {"rice": 18.0, "agroforestry": 26.0}
FIXED_PROJECT_COST_YR = 190_000.0   # validation, verification, registry, ops


def radar_block(site, optical_seasons) -> dict:
    """Detect the water regime from Sentinel-1, and show the two instruments.

    The rice claim is "the field was dry". Until now the page showed a
    confidence the simulator had handed over. This runs a detector that sees
    backscatter and nothing else, and reports what it recovered -- including
    where it refused to call a pass.
    """
    passes = sar_series(site, site.enrolled_on, SERIES_END,
                        awd_lapse_season="Kuruvai", awd_lapse_year=2026)
    truth = sar_truth(site, site.enrolled_on, SERIES_END,
                      awd_lapse_season="Kuruvai", awd_lapse_year=2026)
    detector = WaterRegimeDetector()
    seasons = sar_seasons(site, passes)
    provider = SarProvider.from_passes(seasons, detector=detector)

    calls = [c.to_dict() for c in detector.classify(passes)]
    accuracy = score(detector.classify(passes), truth)

    asserted = {}
    by_year: dict[int, list] = {}
    for s_ in optical_seasons:
        by_year.setdefault(s_.year, []).append(s_)
    for year, ss in by_year.items():
        asserted[year] = round(year_confidence(ss), 4)

    years = sorted(set(asserted) | {y for (y, _) in seasons})
    comparison = []
    for year in years:
        regime = provider.regime(year)
        optical = [s_ for s_ in optical_seasons if s_.year == year]
        clear = sum(s_.clear_revisits for s_ in optical)
        revisits = sum(s_.revisits for s_ in optical)
        comparison.append({
            "year": year,
            "asserted_confidence": asserted.get(year),
            "detected_confidence": (round(regime.adoption_confidence, 4)
                                    if regime else None),
            "optical_coverage": round(clear / revisits, 4) if revisits else None,
            "radar_coverage": (round(regime.coverage, 4) if regime else None),
            "radar_passes": regime.passes if regime else 0,
            "awd_events": len(regime.qualifying_spells) if regime else 0,
        })

    return {
        "provider": provider,
        "passes": passes,
        "instrument": "Sentinel-1 C-band IW, VV+VH, "
                      f"{S1_REVISIT_DAYS}-day revisit",
        "calls": calls,
        "regimes": [provider.regime(y).to_dict() for y in years
                    if provider.regime(y) is not None],
        "comparison": comparison,
        "validation": {k: (round(v, 4) if isinstance(v, float) else v)
                       for k, v in accuracy.items()},
        "note": ("A flooded paddy is a mirror and comes back dark -- until "
                 "the canopy closes, when the stems and the water surface "
                 "form a dihedral and it comes back brighter than a drained "
                 "field. The two responses cross, and around the crossing "
                 "there is no information in VV at all. The detector says so "
                 "instead of guessing."),
        "caveats": [
            "Backscatter is simulated from the same hidden water state the "
            "optical series is drawn from; the detector never sees it.",
            "The validation scores are against that simulation. Real "
            "validation needs field water-level loggers on a sample of "
            "plots.",
        ],
    }


def rice_block() -> dict:
    site = THANJAVUR
    project = as_project(site)
    plot = next(iter(project.plots.values()))

    readings = series(site, site.enrolled_on, SERIES_END,
                      awd_lapse_season="Kuruvai", awd_lapse_year=2026)
    seasons = summarise_seasons(readings)
    radar = radar_block(site, seasons)
    provider = FeedProvider(readings, sar_passes=radar["passes"],
                            adoption=radar["provider"])

    # Roll seasons up to a crediting year, weighting confidence by abatement.
    by_year: dict[int, list] = {}
    for s in seasons:
        by_year.setdefault(s.year, []).append(s)

    vintages = []
    results = []
    for year, ss in sorted(by_year.items()):
        complete = [s for s in ss if s.end <= TODAY]
        abatement_per_ha = sum(s.abatement_tco2e_ha for s in ss)
        confidence = year_confidence(ss)

        # Quantify through the engine under VM0051, the purpose-built rice
        # methodology. The prototype used VM0042; two independent methodology
        # reviews flagged that as wrong. The practical difference is the
        # buffer: avoided methane is not a stock and cannot reverse, so none
        # is withheld.
        baseline = sum(s.baseline_ch4_kg_ha for s in ss) / max(len(ss), 1)
        project_ch4 = sum(s.project_ch4_kg_ha for s in ss) / max(len(ss), 1)
        factor = RiceEmissionFactor(
            baseline_ch4_kg_ha_season=baseline,
            project_ch4_kg_ha_season=project_ch4,
            seasons_per_year=len(ss),
            tier=1,
            source=(f"measured from {sum(s.revisits for s in ss)} revisits across "
                    f"{len(ss)} season(s); {CH4_GWP100}x GWP100"),
        )
        m = methodology.get(
            "VM0051", factors={"awd": factor},
            common_practice=CommonPractice(
                jurisdiction="Tamil Nadu", awd_penetration=0.04,
                source="placeholder -- replace with a cited state-level survey"))
        # The adoption probability is detected from radar, not asserted.
        # Everything above this line is unchanged; what moved is where the
        # number comes from, and it moves the credits with it.
        result = m.quantify(project, provider, year)
        detected = radar["provider"].regime(year)
        confidence = (detected.adoption_confidence if detected is not None
                      else 0.0)

        payload = result.to_dict()
        payload["warnings"] = list(payload["warnings"])
        for s_ in (detected.seasons if detected is not None else []):
            if not s_.qualifying_spells:
                payload["warnings"].append(
                    f"{s_.season} {s_.year}: no AWD event detected across "
                    f"{s_.passes} radar passes -- the practice may not have "
                    f"happened")
            elif s_.adoption_confidence < 0.6:
                payload["warnings"].append(
                    f"{s_.season} {s_.year}: detected adoption confidence "
                    f"{s_.adoption_confidence:.0%}, with "
                    f"{s_.usable_passes} of {s_.passes} passes separable")
        result.warnings = list(payload["warnings"])
        results.append(result)
        vintages.append({
            **payload,
            "complete": len(complete) == len(ss),
            "seasons": [s.to_dict() for s in ss],
            "abatement_tco2e_ha": round(abatement_per_ha, 4),
            "adoption_confidence": round(confidence, 3),
            "asserted_confidence": round(year_confidence(ss), 3),
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
        "_provider": provider,
        "radar": {k: v for k, v in radar.items()
                  if k not in ("provider", "passes")},
        "_results": results,
        "_project": project,
        "methodology": {
            "id": "VM0051",
            "version": "v1.1",
            "name": "Improved Management in Rice Production Systems",
            "note": ("The purpose-built rice methodology, replacing CDM "
                     "AMS-III.AU and CORSIA eligible. No buffer is withheld: "
                     "avoided methane is not a stock and cannot reverse. The "
                     "emission factor is still Tier 1 until local flux "
                     "chambers calibrate it."),
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
    results = []
    for year in range(site.enrolled_on.year + 1, PROJECTION_END.year + 1):
        result = m.quantify(project, long_provider, year)
        payload = result.to_dict()
        payload["warnings"] = list(payload["warnings"]) + [
            f"{year}: {f}" for f in long_provider.flags_near(date(year, 12, 31))
            if "cloud" not in f
        ]
        result.warnings = list(payload["warnings"])
        results.append(result)
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
        "census": census_block(site, project, vintages),
        "_results": results,
        "_project": project,
        "_provider": provider,
        "methodology": {
            "id": "VM0047",
            "version": "v1.1",
            "name": "Afforestation, Reforestation and Revegetation (area-based)",
            "note": ("Credits are growth net of a dynamic performance "
                     "benchmark. Both the benchmark and the allometric "
                     "equation are placeholders."),
        },
    }


# The shade-tree census. Gatugi is a shade-coffee block, so the upper canopy
# is the shade trees and the area-based path can read it. Most of the
# agroforestry pipeline is not like that -- trees on a paddy bund are a line of
# stems narrower than a Sentinel-2 pixel, and an index that returns near zero
# over a thriving planting is not conservative, it is wrong. Running both
# instruments over the one site where both are legitimate is the only way to
# show what the census costs and what it buys.
SHADE_STEMS_PER_HA = 100          # typical Nyeri shade-coffee stocking
CENSUS_SAMPLE = 40                # stems measured per visit
HEIGHT_TO_DBH = 2.0               # cm of diameter per metre of height
FIRST_CENSUS_YEAR = 2026

# A deterministic spread standing in for the variation a field crew measures.
# Fixed rather than random so a rebuild reproduces the committed page exactly.
SPREAD = [1 + (i - (CENSUS_SAMPLE - 1) / 2) * 0.009 for i in range(CENSUS_SAMPLE)]


def _census_visit(site, provider, year: int, stems_planted: int):
    """One annual census, derived from the same feed the area path reads.

    Both instruments see the same trees. Deriving the census from the canopy
    series rather than inventing a second dataset is what makes the comparison
    honest: where they differ, the difference is the instrument.
    """
    on = date(year, 11, 20)
    reading = provider._nearest(on, "canopy_height_m")
    if reading is None or reading.canopy_height_m is None:
        return None
    height = reading.canopy_height_m
    dbh = height * HEIGHT_TO_DBH

    # Mortality is front-loaded: establishment losses, then attrition.
    survival = max(0.80, 0.93 - 0.015 * (year - FIRST_CENSUS_YEAR))
    alive = round(CENSUS_SAMPLE * survival)

    return CensusInventory(
        plot_id=f"{site.id}-P1", measured_on=on,
        survival=SurvivalSurvey(
            plot_id=f"{site.id}-P1", surveyed_on=on,
            stems_planted=stems_planted, stems_sampled=CENSUS_SAMPLE,
            stems_alive=alive, surveyor="field crew, Gatugi"),
        sample=[StemMeasurement("grevillea_robusta",
                                dbh_cm=round(dbh * f, 2),
                                height_m=round(height * f, 2))
                for f in SPREAD])


def census_block(site, project, area_vintages: list[dict]) -> dict:
    """Run the census-based approach beside the area-based one."""
    stems = int(round(site.area_ha * SHADE_STEMS_PER_HA))
    readings = series(site, site.enrolled_on, PROJECTION_END, stumping_year=2026)
    provider = FeedProvider(readings)
    pathway = methodology.census_pathway()

    visits: dict[int, CensusInventory] = {}
    for year in range(FIRST_CENSUS_YEAR, PROJECTION_END.year + 1):
        visit = _census_visit(site, provider, year, stems)
        if visit is not None:
            visits[year] = visit

    rows = []
    vintages = []
    for year, inventory in sorted(visits.items()):
        survey = inventory.survival
        stock, relative = inventory.stock()
        rows.append({
            "year": year,
            "measured_on": inventory.measured_on.isoformat(),
            "mean_dbh_cm": round(sum(m.dbh_cm for m in inventory.sample)
                                 / len(inventory.sample), 2),
            "mean_height_m": round(sum(m.height_m for m in inventory.sample)
                                   / len(inventory.sample), 2),
            "survival_rate": round(survey.survival_rate, 4),
            "survival_lower_bound": round(survey.survival_lower_bound(), 4),
            "stems_credited": survey.surviving_stems,
            "stock_tco2e": round(stock, 3),
            "relative_uncertainty": round(relative, 4),
            "complete": inventory.measured_on <= TODAY,
        })

        prior = visits.get(year - 1)
        result = pathway.quantify(
            project, inventories={inventory.plot_id: inventory},
            prior_inventories=({prior.plot_id: prior} if prior else None),
            reporting_year=year)
        payload = result.to_dict()
        payload["complete"] = date(year, 12, 31) <= TODAY
        vintages.append(payload)

    by_year = {v["year"]: v for v in vintages}
    comparison = [{
        "year": v["year"],
        "area_based_net_t": round(v["net_t"], 3),
        "census_net_t": round(by_year[v["year"]]["net_t"], 3)
        if v["year"] in by_year else None,
    } for v in area_vintages if v["year"] in by_year]

    # The two instruments disagree, and by how much is the finding. The
    # area-based path reads a canopy-height stand fit that assumes a closed
    # canopy; a shade-coffee block at 100 stems/ha does not have one, so it
    # attributes forest biomass to ground that is mostly coffee. The census
    # counts what is there. Where they diverge the census is the floor, and
    # the committed economics -- which run off the area-based path -- are
    # optimistic by roughly this ratio.
    settled = [c for c in comparison if c["census_net_t"]]
    ratio = (sum(c["area_based_net_t"] for c in settled)
             / sum(c["census_net_t"] for c in settled)) if settled else None

    return {
        "approach": "VM0047 v1.1, census-based",
        "instrument_gap": {
            "ratio": round(ratio, 2) if ratio else None,
            "finding": ("The area-based path credits about "
                        f"{ratio:.1f}x what the census does over the same "
                        "trees. Its stand fit assumes a closed canopy; at "
                        f"{SHADE_STEMS_PER_HA} stems/ha this block does not "
                        "have one, so canopy height is reading coffee and "
                        "gaps as forest. The census is the floor, and the "
                        "economics on this site are optimistic by roughly "
                        "that factor." if ratio else ""),
        },
        "stems_planted": stems,
        "stems_per_ha": SHADE_STEMS_PER_HA,
        "sample_size": CENSUS_SAMPLE,
        "allometry": "Chave et al. (2014) pantropical, generic wood density",
        "locally_calibrated": False,
        "benchmark_vetted": pathway.benchmark.is_vetted,
        "visits": rows,
        "vintages": vintages,
        "comparison": comparison,
        "note": ("Both instruments read the same trees. The area-based path "
                 "reads a stocking index off the canopy; the census counts "
                 "stems, measures a sample and credits the lower bound of the "
                 "survival survey. Only one of them works on a bund line, "
                 "which is most of the agroforestry pipeline."),
        "caveats": [
            "Survival and stem measurements are derived from the simulated "
            "canopy series, not from a field crew.",
            "The allometric equation is generic: a local fit is worth roughly "
            "a quarter of the deduction.",
            "The performance benchmark is a placeholder and no issuance may "
            "rest on it.",
        ],
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
            # Cost per issued tonne, not per hectare. Deductions and the
            # buffer decide how many credits actually reach a registry, so a
            # cheap hectare carrying a large deduction is a worse business
            # than a dearer one that issues more.
            cost = mrv + farmer
            return {
                "credits": round(credits, 3),
                "gross_revenue": round(gross, 2),
                "to_farmer": round(farmer, 2),
                "to_developer": round(developer, 2),
                "net_of_mrv": round(developer - mrv, 2),
                "cost_per_issued_tonne": (round(cost / credits, 2)
                                          if credits > 0 else None),
                "revenue_per_issued_tonne": price,
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


def forecast_block(block: dict) -> dict:
    """What this site could safely promise, and what aggregation would buy.

    The page already shows a credit curve. A curve is a projection, and
    nobody sells a projection -- they sell a contract, and a contract needs
    the volume the project clears in nine futures out of ten. On a
    single-plot pilot those two numbers are nothing like each other, and
    the gap is the case for aggregating smallholders.
    """
    site = block["site"]
    projections = forecast.from_vintages(block["vintages"],
                                         track=site["track"])
    if not projections:
        return {}

    risk = forecast.RiskModel()          # one plot, one farmer, one unit
    f = forecast.run(projections, project_id=site["id"], risk=risk,
                     trials=2500)
    curve = forecast.aggregation_curve(projections, risk=risk, trials=800)

    # The offtake a buyer would plausibly ask for: the project's own
    # projection. Showing that it does not clear is the point.
    offtake = forecast.assess_offtake(
        f, projections, committed_t=f.projected_total_t,
        replacement_price=PRICE[site["track"]] * 1.75, risk=risk)

    return {
        **f.to_dict(),
        "aggregation": curve,
        "offtake_at_projection": offtake.to_dict(),
        "note": ("Delivery is simulated against the risks that actually "
                 "stop a credit arriving -- a farmer leaving, a season not "
                 "practised, a planting failing, a verification slipping -- "
                 "not just measurement error. The safe volume is the level "
                 "cleared in nine futures out of ten, and it is what may be "
                 "sold forward."),
        "caveats": [
            "Attrition, lapse and verification rates are placeholders until "
            "the portfolio has its own history.",
            "A single plot is one independently-failing unit, which is why "
            "the haircut is so large; the aggregation curve shows what that "
            "costs.",
        ],
    }


def govern(blocks: list[dict]) -> dict:
    """Run the real lifecycle into a real database, and report what happened.

    The dashboard should not be a second, parallel calculation of the same
    numbers -- that is how two screens end up disagreeing and nobody knows
    which is right. So the governance section is read back out of the store
    after the actual ledger, payment and evidence code has run against it.
    """
    db_path = DASH / "pilot.db"
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        extra = db_path.with_name(db_path.name + suffix)
        if extra.exists():
            extra.unlink()

    out: dict = {"sites": {}}
    with Store(db_path, actor="pipeline") as store:
        for block in blocks:
            site = block["site"]
            project = block["_project"]
            track = site["track"]
            meth = {"rice": "VM0051", "cropland": "VM0042"}.get(track, "VM0047")
            store.save_project(project, methodology_id=meth)

            # Monitor before quantifying, so the evidence pack carries the
            # observations the claim rests on rather than only the totals.
            # For rice that is the radar: water_regime.csv is rebuilt from
            # these rows, and if the database cannot reproduce the call then
            # the call is not evidence.
            monitor_provider = block.get("_provider")
            if monitor_provider is not None:
                pipeline.monitor(
                    store, site["id"], monitor_provider,
                    start=date.fromisoformat(site["enrolled_on"]),
                    end=min(TODAY, SERIES_END), actor="pipeline")

            settled = []
            for result in block["_results"]:
                if date(result.year, 12, 31) > TODAY:
                    continue
                v = ledger.record_vintage(store, result, actor="pipeline")
                ledger.submit_for_review(store, v.id, actor="ops")
                note = ("reviewed: " + "; ".join(v.warnings)) if v.warnings else ""
                if v.warnings:
                    # A warned vintage is held, not waved through. That is the
                    # whole point of the warning existing.
                    ledger.hold(store, v.id, actor="verifier",
                                note="held pending field confirmation")
                    settled.append(ledger.get_vintage(store, v.id))
                    continue
                ledger.approve(store, v.id, actor="verifier", note=note)
                try:
                    ledger.issue(store, v.id,
                                 registry="Gold Standard" if track == "rice" else "Verra",
                                 actor="verifier")
                except StoreError:
                    settled.append(ledger.get_vintage(store, v.id))
                    continue
                terms = payments.PaymentTerms(
                    price_per_credit=PRICE[track],
                    farmer_share=FARMER_SHARE[track])
                payments.raise_payments(store, v.id, terms, actor="finance")
                settled.append(ledger.get_vintage(store, v.id))

            out["sites"][site["id"]] = {
                "vintages": [v.to_dict() for v in settled],
                "issuances": [i.to_dict()
                              for i in ledger.issuances(store, site["id"])],
                "buffer": ledger.buffer_balance(store, site["id"]),
                "payments": [p.to_dict()
                             for p in payments.register(store, project_id=site["id"])],
                "payment_summary": payments.summary(store, site["id"]),
            }

        intact, bad = store.verify_chain()
        events = store.events()
        out["integrity"] = {
            "chain_intact": intact,
            "first_bad_event": bad,
            "event_count": len(events),
            "head_hash": events[-1]["hash"] if events else None,
        }
        out["events"] = [
            {"at": e["at"], "actor": e["actor"], "kind": e["kind"],
             "subject_id": e["subject_id"], "hash": e["hash"][:12]}
            for e in events
        ]
        for block in blocks:
            evidence.build(store, block["site"]["id"],
                           DASH / "packs" / block["site"]["id"])
    return out


def main() -> int:
    rice = rice_block()
    coffee = coffee_block()

    governance = govern([rice, coffee])
    for block in (rice, coffee):
        block["forecast"] = forecast_block(block)
    for block in (rice, coffee):
        block.pop("_results", None)
        block.pop("_project", None)
        block.pop("_provider", None)

    payload = {
        "generated_at": TODAY.isoformat(),
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
        "governance": governance,
    }

    out = Path(os.environ.get("CARBONSTACK_DATA_OUT", ROOT / "dashboard" / "data.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    readable = sum(len(b["readings"]) for b in payload["blocks"])
    try:
        shown = out.relative_to(ROOT)
    except ValueError:
        shown = out
    print(f"wrote {shown}  "
          f"{out.stat().st_size / 1024:.0f} KB, {readable} readings, "
          f"{sum(len(b['vintages']) for b in payload['blocks'])} vintages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
