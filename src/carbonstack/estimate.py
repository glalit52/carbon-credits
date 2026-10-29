"""A credit estimate for any farm, from its boundary and crop calendar.

The pilot sites are hand-built `Site` records with researched climate and
pathway parameters. A customer drawing a polygon in the web app has none of
that, so this module builds the `Site` from what the customer gives plus what
can be looked up for that point on earth:

  * climate: Open-Meteo's ERA5 archive for the last ten complete years, then
    NASA POWER, then caller-supplied normals. A farm whose climate cannot be
    found is refused rather than given somebody else's.
  * pathway parameters: the customer's own figures where they have them,
    otherwise published defaults, each one named in `assumptions` so the
    estimate says which of its inputs are local and which are generic.

Monitoring is still the simulated feed (`feed.series`) -- now driven by the
farm's real climate and calendar instead of a generic growth curve -- and the
result says so in `data_quality`. Swapping in real Sentinel retrievals changes
the provider and nothing here.

Stateless: nothing is written. The web app stores what comes back.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date

from .connectors import ConnectorUnavailable, default_transport, weather
from .domain import RiceEcosystem, TenureBasis, TrackKind, WaterControl
from .feed import FeedProvider, sar_seasons, sar_series, series, summarise_seasons
from .geo import area_ha, centroid, validate_ring
from .sar import SarProvider
from .sites import Climate, Season, Site, as_project

#: IPCC 2019 Refinement, Vol. 4 Ch. 5, Table 5.11: baseline emission factor
#: for continuously flooded rice without organic amendment, global default.
IPCC_EF_CONTINUOUS_FLOOD = 1.19      # kg CH4 / ha / day
#: Table 5.12: scaling factor for multiple drainage periods, i.e. AWD.
IPCC_SF_MULTIPLE_DRAINAGE = 0.55

#: Shade-tree growth defaults: the Gatugi block's Grevillea-dominated stand.
DEFAULT_PEAK_HEIGHT_M = 13.5
DEFAULT_YEARS_TO_HALF = 4.5
DEFAULT_STEMS_PER_HA = 120

CLIMATE_YEARS = 10

PATHWAYS = {"rice": TrackKind.RICE, "agroforestry": TrackKind.AGROFORESTRY}
METHODOLOGY = {"rice": "VM0051", "agroforestry": "VM0047"}


class EstimateError(ValueError):
    """The request cannot be estimated; the message says what to fix."""


@dataclass
class _Climate:
    climate: Climate
    source: str
    quality: str            # 'measured' or 'supplied'
    provenance: list[dict]


def _ring(boundary: dict) -> list[tuple[float, float]]:
    """The outer ring of a GeoJSON Polygon (or the largest of a MultiPolygon)."""
    if not isinstance(boundary, dict):
        raise EstimateError("boundary must be a GeoJSON Polygon or MultiPolygon")
    kind, coords = boundary.get("type"), boundary.get("coordinates")
    try:
        if kind == "Polygon":
            rings = [coords[0]]
        elif kind == "MultiPolygon":
            rings = [poly[0] for poly in coords]
        else:
            raise EstimateError(f"boundary type {kind!r} is not a polygon")
        candidates = [[(float(p[0]), float(p[1])) for p in r] for r in rings]
    except (TypeError, IndexError, ValueError) as exc:
        raise EstimateError(f"boundary coordinates are malformed ({exc})") from exc
    ring = max(candidates, key=area_ha)
    problems = validate_ring(ring)
    if problems:
        raise EstimateError("boundary: " + "; ".join(problems))
    return ring


def _seasons(raw: list[dict] | None, pathway: str) -> tuple[Season, ...]:
    if not raw:
        if pathway == "rice":
            raise EstimateError(
                "rice needs its crop calendar: give each season's start and end "
                "month and day")
        # Trees grow all year; one calendar-year window is enough to read them.
        return (Season("Year", 1, 1, 12, 31),)
    out = []
    for i, s in enumerate(raw):
        try:
            season = Season(str(s.get("name") or f"Season {i + 1}"),
                            int(s["start_month"]), int(s.get("start_day", 1)),
                            int(s["end_month"]), int(s.get("end_day", 28)))
            date(2001, season.start_month, season.start_day)
            date(2001, season.end_month, season.end_day)
        except (KeyError, TypeError, ValueError) as exc:
            raise EstimateError(f"season {i + 1} is not a valid month/day window ({exc})") from exc
        out.append(season)
    return tuple(out)


def _season_days(season: Season) -> int:
    start = date(2001, season.start_month, season.start_day)
    end = date(2002 if season.wraps else 2001, season.end_month, season.end_day)
    return (end - start).days + 1


def _from_series(cs: weather.ClimateSeries) -> Climate:
    normals = cs.normals()
    temps = [m.temp_c for m in normals]
    return Climate(
        monthly_rain_mm=tuple(round(m.rain_mm, 1) for m in normals),
        mean_temp_c=round(math.fsum(temps) / 12, 2),
        temp_amplitude_c=round((max(temps) - min(temps)) / 2, 2))


def _climate(lat: float, lon: float, request: dict, transport, today: date) -> _Climate:
    """The farm's climate, from the best source that answers."""
    source = request.get("climate_source", "auto")
    failures: list[str] = []
    end = date(today.year - 1, 12, 31)
    start = date(end.year - CLIMATE_YEARS + 1, 1, 1)

    if source in ("auto", "open-meteo"):
        try:
            cs = weather.open_meteo(transport, lat, lon, start, end)
            return _Climate(_from_series(cs), cs.source, "measured", cs.provenance)
        except (ConnectorUnavailable, ValueError) as exc:
            failures.append(f"Open-Meteo: {exc}")
    if source in ("auto", "nasa-power"):
        try:
            cs = weather.nasa_power(transport, lat, lon, start.year, end.year)
            return _Climate(_from_series(cs), cs.source, "measured", cs.provenance)
        except (ConnectorUnavailable, ValueError) as exc:
            failures.append(f"NASA POWER: {exc}")

    normals = request.get("climate_normals")
    if normals:
        try:
            rain = tuple(float(x) for x in normals["monthly_rain_mm"])
            if len(rain) != 12:
                raise ValueError("monthly_rain_mm needs twelve values")
            return _Climate(
                Climate(rain, float(normals["mean_temp_c"]),
                        float(normals.get("temp_amplitude_c", 2.0))),
                str(normals.get("label", "supplied normals")), "supplied", [])
        except (KeyError, TypeError, ValueError) as exc:
            raise EstimateError(f"climate_normals are malformed ({exc})") from exc

    raise EstimateError(
        "no climate for this location: " + "; ".join(failures or ["no source tried"])
        + ". Supply climate_normals, or allow the connectors network access.")


def build_site(request: dict, *, transport=None, today: date | None = None) -> tuple[Site, dict]:
    """A `Site` for the farm in `request`, and the record of how it was built."""
    today = today or date.today()
    farm = request.get("farm") or {}
    pathway = str(farm.get("pathway", "")).lower()
    if pathway not in PATHWAYS:
        raise EstimateError(f"pathway must be one of {sorted(PATHWAYS)}")

    ring = _ring(farm.get("boundary"))
    lon, lat = centroid(ring)
    seasons = _seasons(farm.get("seasons"), pathway)
    try:
        enrolled_on = date.fromisoformat(str(farm.get("enrolled_on") or date(today.year, 1, 1)))
    except ValueError as exc:
        raise EstimateError(f"enrolled_on is not a date ({exc})") from exc
    if enrolled_on > today:
        raise EstimateError("enrolled_on is in the future; there is nothing to estimate yet")

    clim = _climate(lat, lon, request, transport or default_transport(), today)
    assumptions: list[dict] = []

    def assume(name: str, value, basis: str) -> None:
        assumptions.append({"parameter": name, "value": value, "basis": basis})

    params = farm.get("parameters") or {}
    extra: dict = {}
    if pathway == "rice":
        days = round(math.fsum(_season_days(s) for s in seasons) / len(seasons))
        baseline = params.get("baseline_ch4_kg_ha_season")
        if baseline is None:
            baseline = round(IPCC_EF_CONTINUOUS_FLOOD * days, 1)
            assume("baseline_ch4_kg_ha_season", baseline,
                   f"IPCC 2019 Tier 1 global default, {IPCC_EF_CONTINUOUS_FLOOD} kg/ha/day "
                   f"over a {days}-day season; replace with a regional or measured factor")
        reduction = params.get("awd_reduction")
        if reduction is None:
            reduction = round(1 - IPCC_SF_MULTIPLE_DRAINAGE, 2)
            assume("awd_reduction", reduction,
                   "IPCC 2019 scaling factor for multiple drainage periods (0.55)")
        ecosystem = farm.get("rice_ecosystem")
        control = farm.get("water_control")
        if ecosystem is None:
            assume("rice_ecosystem", "unknown", "not recorded at enrolment; VM0051 will block it")
        if control is None:
            assume("water_control", "unknown", "not recorded at enrolment; VM0051 will block it")
        extra = {
            "baseline_ch4_kg_ha_season": float(baseline),
            "awd_reduction": float(reduction),
            "ecosystem": RiceEcosystem(ecosystem or "unknown"),
            "water_control": WaterControl(control or "unknown"),
        }
    else:
        peak = params.get("peak_height_m")
        if peak is None:
            peak = DEFAULT_PEAK_HEIGHT_M
            assume("peak_height_m", peak, "Grevillea-dominated shade stand (Gatugi pilot)")
        half = params.get("years_to_half")
        if half is None:
            half = DEFAULT_YEARS_TO_HALF
            assume("years_to_half", half, "Grevillea-dominated shade stand (Gatugi pilot)")
        extra = {"shade_peak_height_m": float(peak), "shade_years_to_half": float(half)}

    tenure = farm.get("tenure") or "undocumented"
    try:
        tenure_basis = TenureBasis(tenure)
    except ValueError as exc:
        raise EstimateError(f"tenure {tenure!r} is not one of "
                            f"{[t.value for t in TenureBasis]}") from exc

    site = Site(
        id=str(farm.get("id") or "FARM")[:40],
        label=str(farm.get("name") or "Farm"),
        country=str(farm.get("country") or ""),
        admin=str(farm.get("region") or ""),
        lat=lat, lon=lon, boundary=ring,
        track=PATHWAYS[pathway],
        crop=str(farm.get("crop") or ""),
        intervention=str(farm.get("practice") or ""),
        climate=clim.climate,
        seasons=seasons,
        tenure=tenure_basis,
        tenure_reference=str(farm.get("tenure_reference") or ""),
        farmer_name=str(farm.get("farmer_name") or "Farmer"),
        village=str(farm.get("village") or ""),
        enrolled_on=enrolled_on,
        species=tuple(farm.get("species") or ()),
        baseline_captured_on=enrolled_on,
        practice_started_on=enrolled_on,
        **{k: v for k, v in extra.items() if k not in ("ecosystem", "water_control")},
        ecosystem=extra.get("ecosystem"),
        water_control=extra.get("water_control"),
    )
    record = {
        "centroid": {"lat": round(lat, 6), "lon": round(lon, 6)},
        "area_ha": round(area_ha(ring), 4),
        "climate": {
            "source": clim.source,
            "quality": clim.quality,
            "monthly_rain_mm": list(clim.climate.monthly_rain_mm),
            "mean_temp_c": clim.climate.mean_temp_c,
            "provenance": clim.provenance,
        },
        "seasons": [{"name": s.name, "start_month": s.start_month, "start_day": s.start_day,
                     "end_month": s.end_month, "end_day": s.end_day} for s in seasons],
        "assumptions": assumptions,
    }
    return site, record


def estimate(request: dict, *, transport=None, today: date | None = None) -> dict:
    """Quantify every requested year for one farm. See the module docstring."""
    today = today or date.today()
    site, record = build_site(request, transport=transport, today=today)
    pathway = str(request["farm"]["pathway"]).lower()
    meth_id = METHODOLOGY[pathway]

    years = request.get("years") or list(range(site.enrolled_on.year, today.year + 1))
    try:
        years = sorted({int(y) for y in years})
    except (TypeError, ValueError) as exc:
        raise EstimateError(f"years must be integers ({exc})") from exc
    if len(years) > 15 or years[0] < site.enrolled_on.year or years[-1] > today.year + 10:
        raise EstimateError("years must start no earlier than enrolment, run at most "
                            "ten years ahead and number fifteen or fewer")

    end = date(max(years), 12, 31)
    readings = series(site, site.enrolled_on, end)
    if pathway == "rice":
        passes = sar_series(site, site.enrolled_on, end)
        provider = FeedProvider(readings, sar_passes=passes,
                                adoption=SarProvider.from_passes(sar_seasons(site, passes)))
    else:
        provider = FeedProvider(readings)

    # Imported here: cli pulls in the whole command surface.
    from .cli import _methodology_for

    # Two runs. `creditable` quantifies the farm exactly as recorded, so
    # missing paperwork excludes it the way a verifier would. `potential`
    # completes the paperwork only -- a tenure reference -- and keeps every
    # physical condition (ecosystem, water control) as given: an upland rice
    # field has no potential under VM0051 however good its documents.
    project = as_project(site)
    paper_complete = as_project(replace(
        site, tenure_reference=site.tenure_reference or "to be collected"))
    blockers = {pid: list(problems) for pid, problems in project.eligibility_issues().items()}

    vintages = []
    for year in years:
        try:
            meth = _methodology_for(site, meth_id, readings, year)
        except SystemExit as exc:          # no season closed in that year
            vintages.append({"year": year, "skipped": str(exc)})
            continue
        if hasattr(meth, "eligibility_issues"):
            for pid, problems in meth.eligibility_issues(project).items():
                blockers.setdefault(pid, [])
                blockers[pid] += [x for x in problems if x not in blockers[pid]]
        result = meth.quantify(project, provider, year).to_dict()
        potential = meth.quantify(paper_complete, provider, year).to_dict()
        result["potential"] = {k: potential[k] for k in
                               ("gross_t", "net_t", "deductions", "relative_uncertainty")}
        result["potential"]["calculations"] = potential["calculations"]
        if year >= today.year:
            result["warnings"].append(
                "projection: this year has not finished, so its monitoring is simulated ahead")
        vintages.append(result)

    seasons = [s.to_dict() for s in summarise_seasons(readings)
               if s.year in years] if pathway == "rice" else []

    quality = ("simulated monitoring on measured climate" if record["climate"]["quality"] == "measured"
               else "simulated monitoring on supplied climate")
    return {
        "methodology": meth_id,
        "pathway": pathway,
        "data_quality": quality,
        # Problems keyed by the engine's own plot id; the app has one farm.
        "blockers": sorted({x for problems in blockers.values() for x in problems}),
        "site": record,
        "vintages": vintages,
        "seasons": seasons,
        "totals": {
            "creditable_net_t": round(math.fsum(v.get("net_t", 0.0) for v in vintages), 4),
            "potential_gross_t": round(math.fsum(
                v["potential"]["gross_t"] for v in vintages if "potential" in v), 4),
            "potential_net_t": round(math.fsum(
                v["potential"]["net_t"] for v in vintages if "potential" in v), 4),
        },
        "notes": [
            "Monitoring values are simulated from this farm's climate and calendar; "
            "satellite retrievals replace them when a live provider is connected.",
            "An estimate is not a vintage: nothing here has been reviewed or issued.",
        ] + ([
            "Area-based VM0047 reads the canopy. Scattered trees (bunds, shade rows) "
            "need a stem census instead, which on the Gatugi pilot credited about a "
            "fifth of this figure.",
        ] if pathway == "agroforestry" else []),
    }
