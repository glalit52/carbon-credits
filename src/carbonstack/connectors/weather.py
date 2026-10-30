"""Monthly weather for a point: what a soil model and a rice baseline run on.

Two sources, both free, both reanalysis rather than station data:

* **Open-Meteo archive** -- ERA5 / ERA5-Land, daily, from 1940. Returns FAO-56
  reference evapotranspiration directly, which is the term RothC's moisture
  deficit needs and the one that is hardest to get right by hand.
* **NASA POWER** -- MERRA-2 based, monthly endpoint, agronomy community. No
  reference ET, so evaporation is estimated with Thornthwaite and *marked* as
  estimated, because Thornthwaite under-reads the hot dry season and the
  derivation should say so rather than hide it.

And one offline source, `from_normals`, that turns a site's published monthly
climatology into the same shape. It is labelled as climatology everywhere it
goes. A soil projection run on normals is a forecast; one run on retrieved
monthly weather is a hindcast; the two are not interchangeable in a monitoring
report and the label is what keeps them apart.
"""

from __future__ import annotations

import calendar
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .base import ConnectorUnavailable, Snapshot, Transport


@dataclass(frozen=True)
class MonthlyWeather:
    year: int
    month: int
    temp_c: float
    rain_mm: float
    pet_mm: float            # reference / potential evapotranspiration
    pet_method: str          # "fao56" | "thornthwaite" | "normals"

    @property
    def key(self) -> tuple[int, int]:
        return (self.year, self.month)


@dataclass
class ClimateSeries:
    """Monthly weather with where it came from."""

    lat: float
    lon: float
    months: list[MonthlyWeather]
    source: str
    provenance: list[dict] = field(default_factory=list)
    is_climatology: bool = False

    def __post_init__(self) -> None:
        self.months.sort(key=lambda m: m.key)

    @property
    def span(self) -> tuple[tuple[int, int], tuple[int, int]] | None:
        if not self.months:
            return None
        return self.months[0].key, self.months[-1].key

    def normals(self) -> list[MonthlyWeather]:
        """Twelve mean months. What a forward projection repeats.

        Only whole months are averaged and every calendar month must be
        present, because a "normal" July computed from no Julys is a made-up
        July.
        """
        by_month: dict[int, list[MonthlyWeather]] = defaultdict(list)
        for m in self.months:
            by_month[m.month].append(m)
        missing = [calendar.month_abbr[i] for i in range(1, 13) if not by_month[i]]
        if missing:
            raise ValueError(f"cannot form normals: no data for {', '.join(missing)}")
        out = []
        for i in range(1, 13):
            ms = by_month[i]
            out.append(MonthlyWeather(
                0, i,
                math.fsum(m.temp_c for m in ms) / len(ms),
                math.fsum(m.rain_mm for m in ms) / len(ms),
                math.fsum(m.pet_mm for m in ms) / len(ms),
                ms[0].pet_method))
        return out

    def annual_rain_mm(self) -> float:
        years = {m.year for m in self.months}
        return math.fsum(m.rain_mm for m in self.months) / max(1, len(years))

    def to_dict(self) -> dict:
        return {
            "lat": self.lat, "lon": self.lon, "source": self.source,
            "is_climatology": self.is_climatology,
            "months": [
                {"year": m.year, "month": m.month, "temp_c": round(m.temp_c, 2),
                 "rain_mm": round(m.rain_mm, 1), "pet_mm": round(m.pet_mm, 1),
                 "pet_method": m.pet_method}
                for m in self.months
            ],
            "provenance": self.provenance,
        }


# ---------------------------------------------------------------------------
# Thornthwaite, for sources that do not supply evapotranspiration
# ---------------------------------------------------------------------------

def thornthwaite_pet(monthly_temp_c: list[float], lat: float) -> list[float]:
    """Potential evapotranspiration, mm/month, for twelve mean temperatures.

    PET = 16 * (L/12) * (N/30) * (10 T / I)^a, with I the annual heat index
    and L the mean daylength for the month at this latitude. Simple, needs
    only temperature, and known to under-read in hot dry months -- which is
    why the method travels with the number.
    """
    if len(monthly_temp_c) != 12:
        raise ValueError("Thornthwaite needs twelve monthly temperatures")
    heat = math.fsum((max(t, 0.0) / 5.0) ** 1.514 for t in monthly_temp_c)
    if heat <= 0:
        return [0.0] * 12
    a = (6.75e-7 * heat ** 3 - 7.71e-5 * heat ** 2 + 1.792e-2 * heat + 0.49239)
    out = []
    for i, t in enumerate(monthly_temp_c):
        if t <= 0:
            out.append(0.0)
            continue
        mid = date(2001, i + 1, 15).timetuple().tm_yday
        decl = 0.409 * math.sin(2 * math.pi * mid / 365 - 1.39)
        x = -math.tan(math.radians(lat)) * math.tan(decl)
        ws = math.acos(max(-1.0, min(1.0, x)))
        daylength = 24 / math.pi * ws
        days = calendar.monthrange(2001, i + 1)[1]
        if t >= 26.5:
            # Willmott's high-temperature branch; the power law runs away above it.
            pet = -415.85 + 32.24 * t - 0.43 * t * t
        else:
            pet = 16 * (10 * t / heat) ** a
        out.append(pet * (daylength / 12) * (days / 30))
    return out


# ---------------------------------------------------------------------------
# Open-Meteo archive (ERA5)
# ---------------------------------------------------------------------------

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_DAILY = "temperature_2m_mean,precipitation_sum,et0_fao_evapotranspiration"


def open_meteo(transport: Transport, lat: float, lon: float,
               start: date, end: date) -> ClimateSeries:
    """Daily ERA5 aggregated to whole months.

    A month with any missing day is dropped rather than averaged over the
    days that arrived, and the gap is reported, because a rainfall total
    over 27 days is not a monthly total.
    """
    params = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
              "start_date": start.isoformat(), "end_date": end.isoformat(),
              "daily": OPEN_METEO_DAILY, "timezone": "UTC"}
    snap = transport.fetch("open-meteo", OPEN_METEO_URL, params)
    return parse_open_meteo(snap, lat, lon)


def parse_open_meteo(snap: Snapshot, lat: float, lon: float) -> ClimateSeries:
    data = snap.json()
    if data.get("error"):
        raise ConnectorUnavailable("open-meteo", str(data.get("reason", "error")))
    daily = data.get("daily") or {}
    times = daily.get("time") or []
    temps = daily.get("temperature_2m_mean") or []
    rain = daily.get("precipitation_sum") or []
    et0 = daily.get("et0_fao_evapotranspiration") or []
    if not times or not (len(times) == len(temps) == len(rain) == len(et0)):
        raise ConnectorUnavailable("open-meteo", "daily arrays missing or misaligned")

    buckets: dict[tuple[int, int], list[tuple[float, float, float]]] = defaultdict(list)
    for t, tc, r, e in zip(times, temps, rain, et0):
        if tc is None or r is None or e is None:
            continue
        d = date.fromisoformat(t)
        buckets[(d.year, d.month)].append((tc, r, e))

    months = []
    for (y, m), rows in sorted(buckets.items()):
        if len(rows) < calendar.monthrange(y, m)[1]:
            continue
        months.append(MonthlyWeather(
            y, m,
            math.fsum(r[0] for r in rows) / len(rows),
            math.fsum(r[1] for r in rows),
            math.fsum(r[2] for r in rows),
            "fao56"))
    if not months:
        raise ConnectorUnavailable("open-meteo", "no complete month in the response")
    return ClimateSeries(lat, lon, months, "Open-Meteo ERA5 archive",
                         [snap.provenance()])


# ---------------------------------------------------------------------------
# NASA POWER (monthly)
# ---------------------------------------------------------------------------

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
POWER_MISSING = -999.0


def nasa_power(transport: Transport, lat: float, lon: float,
               start_year: int, end_year: int) -> ClimateSeries:
    params = {"parameters": "T2M,PRECTOTCORR", "community": "AG",
              "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
              "start": str(start_year), "end": str(end_year), "format": "JSON"}
    snap = transport.fetch("nasa-power", NASA_POWER_URL, params)
    return parse_nasa_power(snap, lat, lon)


def parse_nasa_power(snap: Snapshot, lat: float, lon: float) -> ClimateSeries:
    data = snap.json()
    try:
        params = data["properties"]["parameter"]
        t2m, prec = params["T2M"], params["PRECTOTCORR"]
    except (KeyError, TypeError) as exc:
        raise ConnectorUnavailable("nasa-power", f"unexpected response shape ({exc})") from exc

    by_year: dict[int, dict[int, tuple[float, float]]] = defaultdict(dict)
    for key, temp in t2m.items():
        y, m = int(key[:4]), int(key[4:])
        if m == 13:                           # POWER's annual summary column
            continue
        rate = prec.get(key, POWER_MISSING)
        if temp == POWER_MISSING or rate == POWER_MISSING:
            continue
        # PRECTOTCORR is a mean daily rate in mm/day.
        by_year[y][m] = (temp, rate * calendar.monthrange(y, m)[1])

    months = []
    for y, ms in sorted(by_year.items()):
        if len(ms) != 12:
            continue                           # Thornthwaite needs the whole year
        pet = thornthwaite_pet([ms[m][0] for m in range(1, 13)], lat)
        for m in range(1, 13):
            months.append(MonthlyWeather(y, m, ms[m][0], ms[m][1], pet[m - 1],
                                         "thornthwaite"))
    if not months:
        raise ConnectorUnavailable("nasa-power", "no complete year in the response")
    return ClimateSeries(lat, lon, months, "NASA POWER monthly (MERRA-2)",
                         [snap.provenance()])


# ---------------------------------------------------------------------------
# Offline: a site's published normals
# ---------------------------------------------------------------------------

def from_normals(lat: float, lon: float, monthly_rain_mm: tuple[float, ...],
                 mean_temp_c: float, temp_amplitude_c: float,
                 *, label: str = "site climatology") -> ClimateSeries:
    """Twelve months of climatology in the connector's shape.

    Temperature is a sinusoid around the annual mean, peaking in the local
    summer (July north of the equator, January south of it). Rough, which is
    why it is labelled.
    """
    peak = 7 if lat >= 0 else 1
    temps = [mean_temp_c + temp_amplitude_c * math.cos(2 * math.pi * (m - peak) / 12)
             for m in range(1, 13)]
    pet = thornthwaite_pet(temps, lat)
    months = [MonthlyWeather(0, m, temps[m - 1], monthly_rain_mm[m - 1],
                             pet[m - 1], "normals")
              for m in range(1, 13)]
    return ClimateSeries(lat, lon, months, label, is_climatology=True)
