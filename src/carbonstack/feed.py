"""The monitoring feed.

Generates the observation series a Sentinel-2 + Sentinel-1 + GEDI pipeline
would produce for a site, on the real 5-day Sentinel-2 revisit cadence,
driven by that site's published climatology and its actual crop calendar.

This is simulation, and the dashboard says so on its face. It exists because
the quantification engine, the review workflow and the dashboard all need a
realistic feed to be built and tested against, and because the shape of the
data -- how a dry-down looks, how cloud gaps fall, how a pruning event reads
as a canopy loss -- is what the product has to handle correctly. Swapping in
a real provider changes where these numbers come from and nothing else.

Determinism is deliberate: the series is a pure function of site and date, so
the dashboard shows a genuinely new reading each time a real revisit date
passes, and two people looking at the same day see the same number.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from .domain import TrackKind
from .sites import Site

REVISIT_DAYS = 5           # Sentinel-2 A+B combined revisit at these latitudes
CH4_GWP100 = 28.0          # IPCC AR5, methane over 100 years


def _noise(site_id: str, d: date, salt: str) -> float:
    """Deterministic pseudo-random value in [-1, 1]."""
    key = f"{site_id}:{d.isoformat()}:{salt}".encode()
    digest = hashlib.sha256(key).digest()
    return (int.from_bytes(digest[:4], "big") / 0xFFFFFFFF) * 2 - 1


def _cloud_gap(site: Site, d: date) -> bool:
    """Optical retrieval lost to cloud.

    Loss is seasonal -- monsoon and long-rains months lose most passes -- which
    is the single biggest practical problem with optical monitoring in the
    tropics and the reason SAR belongs in the stack. Modelled, not hidden.
    """
    rain = site.climate.rain_for(d.month)
    p_cloud = min(0.72, 0.06 + rain / 320.0)
    return (_noise(site.id, d, "cloud") + 1) / 2 < p_cloud


@dataclass
class Reading:
    """One monitoring timestep for one site."""

    day: date
    rain_mm: float
    temp_c: float
    ndvi: float | None                 # None when the pass was lost to cloud
    soil_moisture: float
    # Rice
    surface_water_frac: float | None = None
    dry_down: bool = False
    ch4_baseline_kg_ha_day: float = 0.0
    ch4_project_kg_ha_day: float = 0.0
    season: str = ""
    season_progress: float = 0.0
    # Coffee
    canopy_height_m: float | None = None
    canopy_uncertainty_m: float | None = None
    # Shared
    source: str = "sentinel2+sentinel1"
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        out = {
            "day": self.day.isoformat(),
            "rain_mm": round(self.rain_mm, 1),
            "temp_c": round(self.temp_c, 1),
            "ndvi": round(self.ndvi, 3) if self.ndvi is not None else None,
            "soil_moisture": round(self.soil_moisture, 3),
            "season": self.season,
            "season_progress": round(self.season_progress, 3),
            "source": self.source,
            "flags": list(self.flags),
        }
        if self.surface_water_frac is not None:
            out |= {
                "surface_water_frac": round(self.surface_water_frac, 3),
                "dry_down": self.dry_down,
                "ch4_baseline_kg_ha_day": round(self.ch4_baseline_kg_ha_day, 4),
                "ch4_project_kg_ha_day": round(self.ch4_project_kg_ha_day, 4),
            }
        if self.canopy_height_m is not None:
            out |= {
                "canopy_height_m": round(self.canopy_height_m, 3),
                "canopy_uncertainty_m": round(self.canopy_uncertainty_m or 0, 3),
            }
        return out


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

def _weather(site: Site, d: date, days: int) -> tuple[float, float]:
    """Rainfall over the step, and mean temperature."""
    normal = site.climate.rain_for(d.month) * days / 30.0
    # Rainfall is bursty: most steps below normal, a few well above.
    u = (_noise(site.id, d, "rain") + 1) / 2
    burst = (u ** 2.6) * 3.4
    rain = max(0.0, normal * burst)

    # Warmest before the rains, coolest during them.
    phase = math.sin(2 * math.pi * (d.timetuple().tm_yday - 100) / 365.0)
    temp = (site.climate.mean_temp_c
            + site.climate.temp_amplitude_c * phase
            + 0.9 * _noise(site.id, d, "temp")
            - min(2.2, rain / 60.0))
    return rain, temp


# ---------------------------------------------------------------------------
# Rice
# ---------------------------------------------------------------------------

def _rice_reading(site: Site, d: date, days: int, *, awd_active: bool) -> Reading:
    rain, temp = _weather(site, d, days)

    season = ""
    progress = 0.0
    for s in site.seasons:
        if s.contains(d):
            season, progress = s.name, s.progress(d)
            break

    if not season:
        # Fallow: bare or stubble, no standing water, no methanogenesis.
        ndvi = 0.18 + 0.07 * (_noise(site.id, d, "ndvi") + 1) / 2 + min(0.08, rain / 260)
        r = Reading(day=d, rain_mm=rain, temp_c=temp, ndvi=ndvi,
                    soil_moisture=0.22 + min(0.3, rain / 130),
                    surface_water_frac=0.03 + min(0.12, rain / 400),
                    season="fallow")
        if _cloud_gap(site, d):
            r.ndvi = None
            r.flags.append("optical pass lost to cloud")
        return r

    # Canopy: transplant, tiller, peak near two thirds, then senesce.
    ndvi = 0.20 + 0.66 * math.sin(math.pi * min(1.0, progress ** 0.82)) ** 0.75
    ndvi = max(0.18, min(0.92, ndvi + 0.03 * _noise(site.id, d, "ndvi")))

    # Water regime. Baseline is continuous flooding for most of the season.
    baseline_water = 0.88 if progress < 0.88 else 0.25

    water = baseline_water
    dry_down = False
    if awd_active and 0.12 < progress < 0.85:
        # Three to four dry-downs a season, each held for one or two revisits.
        cycle = math.sin(progress * math.pi * 7.0 + 0.6)
        if cycle > 0.55:
            water = 0.10 + 0.12 * (_noise(site.id, d, "awd") + 1) / 2
            dry_down = True
    # Heavy rain re-floods a field regardless of intent -- a real reason
    # adoption confidence should never be a hard yes.
    if rain > 55:
        water = max(water, 0.62)
        if dry_down:
            dry_down = False

    # Methane scales with anaerobic water, soil temperature and crop stage
    # (root exudates peak mid-season).
    stage = math.sin(math.pi * min(1.0, progress ** 0.9))
    temp_factor = math.exp(0.055 * (temp - 26.0))
    per_season_days = 110.0
    peak_daily = site.baseline_ch4_kg_ha_season / (per_season_days * 0.62)

    ch4_base = peak_daily * baseline_water * stage * temp_factor
    ch4_proj = peak_daily * water * stage * temp_factor

    r = Reading(
        day=d, rain_mm=rain, temp_c=temp, ndvi=ndvi,
        soil_moisture=0.35 + 0.55 * water,
        surface_water_frac=water, dry_down=dry_down,
        ch4_baseline_kg_ha_day=ch4_base, ch4_project_kg_ha_day=ch4_proj,
        season=season, season_progress=progress,
    )
    if _cloud_gap(site, d):
        r.ndvi = None
        r.flags.append("optical pass lost to cloud; water state from SAR")
        r.source = "sentinel1"
    if rain > 55 and season:
        r.flags.append("heavy rain re-flooded the field")
    return r


# ---------------------------------------------------------------------------
# Coffee agroforestry
# ---------------------------------------------------------------------------

def _coffee_reading(site: Site, d: date, days: int, *,
                    stumping_year: int | None) -> Reading:
    rain, temp = _weather(site, d, days)

    age = (d - site.enrolled_on).days / 365.25
    peak = site.shade_peak_height_m
    k = 0.42
    x = max(-60.0, min(60.0, k * (age - site.shade_years_to_half)))
    height = peak / (1 + math.exp(-x)) if age > 0 else 0.0

    # Shade trees are pollarded for timber and light management. It is a real
    # management event that reads as canopy loss, and the engine must not
    # mistake it for deforestation.
    flags: list[str] = []
    if stumping_year is not None and d.year == stumping_year and d.month in (7, 8):
        height *= 0.62
        flags.append("shade pollarding -- managed canopy reduction, not loss")

    # Retrieval error: worse for short canopies, worse in the wet season.
    sigma = max(0.55, 0.16 * height) * (1.0 + min(0.5, rain / 150.0))

    season = ""
    progress = 0.0
    for s in site.seasons:
        if s.contains(d):
            season, progress = s.name, s.progress(d)
            break

    # Evergreen understory, greening a few weeks behind each rain peak.
    base = 0.58 + 0.10 * min(1.0, age / 4.0)
    ndvi = base + 0.13 * math.sin(math.pi * progress) if season else base - 0.04
    ndvi = max(0.35, min(0.90, ndvi + 0.025 * _noise(site.id, d, "ndvi")))

    r = Reading(
        day=d, rain_mm=rain, temp_c=temp, ndvi=ndvi,
        soil_moisture=0.28 + min(0.42, rain / 110.0),
        canopy_height_m=height, canopy_uncertainty_m=sigma,
        season=season or "dry", season_progress=progress,
        source="sentinel2+gedi", flags=flags,
    )
    if _cloud_gap(site, d):
        r.ndvi = None
        r.canopy_uncertainty_m = sigma * 1.8
        r.flags.append("optical pass lost to cloud; height interpolated")
    return r


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

def series(site: Site, start: date, end: date, *,
           awd_lapse_season: str | None = None,
           awd_lapse_year: int | None = None,
           stumping_year: int | None = None) -> list[Reading]:
    """Every revisit between two dates.

    The lapse and pollarding arguments inject the two situations a review
    workflow exists for: a season where the farmer did not in fact practise
    the intervention, and a management event that looks like a loss. A demo
    without them would only prove the happy path.
    """
    out: list[Reading] = []
    d = start
    while d <= end:
        if site.track is TrackKind.RICE:
            in_lapse = (
                awd_lapse_year is not None
                and d.year == awd_lapse_year
                and any(s.name == awd_lapse_season and s.contains(d)
                        for s in site.seasons)
            )
            r = _rice_reading(site, d, REVISIT_DAYS, awd_active=not in_lapse)
            if in_lapse:
                r.flags.append("no dry-down detected this season")
        else:
            r = _coffee_reading(site, d, REVISIT_DAYS, stumping_year=stumping_year)
        out.append(r)
        d += timedelta(days=REVISIT_DAYS)
    return out


def next_revisit(readings: list[Reading], after: date) -> date:
    """When the next satellite pass is due. Real cadence, so a real countdown."""
    if not readings:
        return after + timedelta(days=REVISIT_DAYS)
    for r in readings:
        if r.day > after:
            return r.day
    return readings[-1].day + timedelta(days=REVISIT_DAYS)


# ---------------------------------------------------------------------------
# Season roll-ups -- what quantification actually consumes
# ---------------------------------------------------------------------------

@dataclass
class SeasonSummary:
    """One rice season, reduced to the numbers a methodology needs."""

    year: int
    season: str
    start: date
    end: date
    revisits: int
    clear_revisits: int
    dry_down_events: int
    baseline_ch4_kg_ha: float
    project_ch4_kg_ha: float
    adoption_confidence: float

    @property
    def reduction_frac(self) -> float:
        if self.baseline_ch4_kg_ha <= 0:
            return 0.0
        return 1 - self.project_ch4_kg_ha / self.baseline_ch4_kg_ha

    @property
    def abatement_tco2e_ha(self) -> float:
        delta_kg = self.baseline_ch4_kg_ha - self.project_ch4_kg_ha
        return delta_kg * CH4_GWP100 / 1000.0

    def to_dict(self) -> dict:
        return {
            "year": self.year, "season": self.season,
            "start": self.start.isoformat(), "end": self.end.isoformat(),
            "revisits": self.revisits, "clear_revisits": self.clear_revisits,
            "dry_down_events": self.dry_down_events,
            "baseline_ch4_kg_ha": round(self.baseline_ch4_kg_ha, 2),
            "project_ch4_kg_ha": round(self.project_ch4_kg_ha, 2),
            "reduction_frac": round(self.reduction_frac, 4),
            "abatement_tco2e_ha": round(self.abatement_tco2e_ha, 4),
            "adoption_confidence": round(self.adoption_confidence, 3),
        }


def summarise_seasons(readings: list[Reading]) -> list[SeasonSummary]:
    """Group a rice series into seasons and integrate the flux."""
    buckets: dict[tuple[int, str], list[Reading]] = {}
    for r in readings:
        if not r.season or r.season == "fallow":
            continue
        # A wrapping season (Samba runs into January) is keyed to its start year.
        year = r.day.year if r.season_progress > 0.06 or r.day.month > 3 else r.day.year - 1
        buckets.setdefault((year, r.season), []).append(r)

    summaries: list[SeasonSummary] = []
    for (year, season), rs in sorted(buckets.items()):
        if len(rs) < 4:
            continue
        base = sum(r.ch4_baseline_kg_ha_day for r in rs) * REVISIT_DAYS
        proj = sum(r.ch4_project_kg_ha_day for r in rs) * REVISIT_DAYS
        dry = sum(1 for r in rs if r.dry_down)

        # Confidence is evidence-driven: how many dry-downs were seen, and how
        # much of the season the satellite actually saw. Both matter, and a
        # season monitored through cloud should not credit like a clear one.
        # Note for whoever rolls these up: weight by baseline exposure, never
        # by achieved abatement. A lapsed season abates nothing, so an
        # abatement-weighted average gives it zero weight and it disappears
        # from the year's confidence entirely -- which is exactly how a
        # project over-credits without anyone deciding to.
        clear = sum(1 for r in rs if r.ndvi is not None)
        coverage = clear / len(rs)
        event_score = min(1.0, dry / 3.0)
        confidence = max(0.0, min(1.0, 0.35 * coverage + 0.65 * event_score))

        summaries.append(SeasonSummary(
            year=year, season=season, start=rs[0].day, end=rs[-1].day,
            revisits=len(rs), clear_revisits=clear, dry_down_events=dry,
            baseline_ch4_kg_ha=base, project_ch4_kg_ha=proj,
            adoption_confidence=confidence,
        ))
    return summaries


# ---------------------------------------------------------------------------
# Bridging the feed into quantification
# ---------------------------------------------------------------------------

class FeedProvider:
    """Serves a generated series through the standard Provider interface.

    The point of the interface is that quantification cannot tell where a
    number came from. This class and a real Sentinel-2 client are
    interchangeable from the engine's side, which is what makes the switch a
    configuration change rather than a rewrite.
    """

    name = "feed"

    def __init__(self, readings: list[Reading], *,
                 season_confidence: dict[int, float] | None = None):
        self._by_day = {r.day: r for r in readings}
        self._readings = sorted(readings, key=lambda r: r.day)
        self._season_confidence = season_confidence or {}

    WINDOW_DAYS = 30

    def _nearest(self, on: date, variable: str) -> Reading | None:
        """Best retrieval in a window ending at the date.

        A real pipeline composites over a window rather than trusting whichever
        pass happens to land on the reporting date -- if that one pass was
        cloudy, a single-date rule hands quantification its worst measurement
        of the year and the uncertainty deduction swings wildly between
        vintages for no physical reason. We take the lowest-uncertainty
        retrieval in the window, which is both more stable and closer to what
        a verifier would accept.
        """
        window_start = on - timedelta(days=self.WINDOW_DAYS)
        candidates = [
            r for r in self._readings
            if window_start <= r.day <= on
            and not (variable == "canopy_height_m" and r.canopy_height_m is None)
        ]
        if not candidates:
            # Fall back to the most recent reading of any quality.
            prior = [r for r in self._readings
                     if r.day <= on
                     and not (variable == "canopy_height_m" and r.canopy_height_m is None)]
            return prior[-1] if prior else None
        return min(candidates,
                   key=lambda r: (r.canopy_uncertainty_m
                                  if r.canopy_uncertainty_m is not None else 0.0))

    def flags_near(self, on: date, window_days: int = 190) -> list[str]:
        """Anything the feed flagged in the run-up to a reporting date.

        A management event or a run of lost passes does not change the
        year-end arithmetic, but a reviewer still has to see it before the
        vintage is signed off.
        """
        start = on - timedelta(days=window_days)
        seen: list[str] = []
        for r in self._readings:
            if start <= r.day <= on:
                for f in r.flags:
                    label = f.split(";")[0].strip()
                    if label not in seen:
                        seen.append(label)
        return seen

    def retrieve(self, plot, variable: str, on: date):
        from .remote_sensing import Retrieval

        if variable == "canopy_height_m":
            r = self._nearest(on, variable)
            if r is None or r.canopy_height_m is None:
                return None
            return Retrieval(plot.id, variable, r.canopy_height_m, "m",
                             r.canopy_uncertainty_m or 0.5, r.day,
                             "sentinel2+gedi")

        if variable == "practice_adopted":
            confidence = self._season_confidence.get(on.year)
            if confidence is None:
                return None
            return Retrieval(plot.id, variable, confidence, "probability",
                             0.08, on, "sentinel1+sentinel2")

        return None


def year_confidence(seasons: list[SeasonSummary]) -> float:
    """Adoption confidence for a crediting year, across its seasons.

    Weighted by baseline methane exposure, deliberately. The tempting weight
    is achieved abatement, and it is wrong in a way that is hard to see: a
    season where the farmer did not practise AWD abates nothing, carries zero
    weight, and vanishes from the average -- so a year containing one good
    season and one lapsed season scores as though the lapse never happened.
    Weighting by what the season could have abated keeps the lapse in view and
    drags the year down, which is the honest answer.
    """
    if not seasons:
        return 0.0
    weight = sum(s.baseline_ch4_kg_ha for s in seasons)
    if weight <= 0:
        return min(s.adoption_confidence for s in seasons)
    return sum(s.adoption_confidence * s.baseline_ch4_kg_ha for s in seasons) / weight
