"""Two real places, at the scale a pilot actually starts.

Both sites are real locations with real coordinates, real crop calendars and
real climate regimes. The plot boundaries are drawn, not surveyed, and every
monitored value is generated -- see feed.py. Nothing here is a measurement.

Why these two:

  Thanjavur, Tamil Nadu -- the Cauvery delta, and rice is India's single
  largest agricultural methane source. Flooded paddy is where the country's
  farm emissions concentrate, which makes it the highest-value place to prove
  an avoidance pathway. Two crops a year, so the evidence loop is months.

  Nyeri, Kenya -- Central Highlands arabica under Grevillea shade. Coffee
  agroforestry is a removal pathway on land already under permanent crop, so
  tenure is cleaner than open reforestation and the trees have a cash reason
  to exist beyond carbon. Bimodal rainfall gives two distinct growing peaks a
  year, which is a harder monitoring problem than one and therefore a better
  test.

Both plots are 2-3 ha. At that size a single plot is nowhere near viable on
its own -- that is the finding, not an oversight, and economics.py states it
in numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .domain import (
    Enrollment, Farmer, Plot, Project, TenureBasis, TrackKind,
)
from .geo import Ring


@dataclass(frozen=True)
class Season:
    """A cropping or growth window within the year."""

    name: str
    start_month: int
    start_day: int
    end_month: int
    end_day: int

    def contains(self, d: date) -> bool:
        start = (self.start_month, self.start_day)
        end = (self.end_month, self.end_day)
        here = (d.month, d.day)
        if start <= end:
            return start <= here <= end
        return here >= start or here <= end   # wraps the new year

    def progress(self, d: date) -> float:
        """0 at the start of the window, 1 at the end. Outside it, 0."""
        if not self.contains(d):
            return 0.0
        y = d.year
        start = date(y, self.start_month, self.start_day)
        end = date(y, self.end_month, self.end_day)
        if end < start:                       # wrapping window
            if (d.month, d.day) >= (self.start_month, self.start_day):
                end = date(y + 1, self.end_month, self.end_day)
            else:
                start = date(y - 1, self.start_month, self.start_day)
        span = (end - start).days or 1
        return min(1.0, max(0.0, (d - start).days / span))


@dataclass(frozen=True)
class Climate:
    """Monthly rainfall normals, mm. Real published climatology, rounded."""

    monthly_rain_mm: tuple[float, ...]
    mean_temp_c: float
    temp_amplitude_c: float

    def rain_for(self, month: int) -> float:
        return self.monthly_rain_mm[month - 1]


@dataclass
class Site:
    """A pilot site: where it is, what grows, and what we are changing."""

    id: str
    label: str
    country: str
    admin: str
    lat: float
    lon: float
    boundary: Ring
    track: TrackKind
    crop: str
    intervention: str
    climate: Climate
    seasons: tuple[Season, ...]
    tenure: TenureBasis
    tenure_reference: str
    farmer_name: str
    village: str
    enrolled_on: date
    species: tuple[str, ...] = ()
    notes: str = ""
    # Pathway parameters, sourced in docs/research/.
    baseline_ch4_kg_ha_season: float = 0.0
    awd_reduction: float = 0.0
    shade_peak_height_m: float = 0.0
    shade_years_to_half: float = 0.0

    @property
    def area_ha(self) -> float:
        from .geo import area_ha
        return area_ha(self.boundary)


# ---------------------------------------------------------------------------
# Boundaries
#
# Drawn as slightly irregular polygons rather than rectangles, because real
# enrolment data is irregular and a pipeline that only ever sees clean squares
# has not been tested.
# ---------------------------------------------------------------------------

def _plot(lon: float, lat: float, width_m: float, height_m: float,
          skew: float = 0.12) -> Ring:
    import math
    dlon = width_m / (111_320.0 * math.cos(math.radians(lat)))
    dlat = height_m / 110_574.0
    return [
        (lon, lat),
        (lon + dlon, lat + dlat * skew * 0.4),
        (lon + dlon * 0.94, lat + dlat),
        (lon + dlon * 0.30, lat + dlat * (1 + skew * 0.25)),
        (lon - dlon * 0.03, lat + dlat * 0.62),
    ]


THANJAVUR = Site(
    id="IN-TNJ-01",
    label="Vallam paddy block",
    country="India",
    admin="Thanjavur district, Tamil Nadu",
    lat=10.7867,
    lon=79.1378,
    boundary=_plot(79.1378, 10.7867, width_m=214, height_m=126),
    track=TrackKind.RICE,
    crop="Paddy rice (ADT-45, CR-1009)",
    intervention="Alternate wetting and drying, field-tube monitored",
    climate=Climate(
        # Thanjavur: north-east monsoon dominant, Oct-Dec.
        monthly_rain_mm=(23, 14, 12, 27, 55, 38, 55, 108, 122, 191, 233, 96),
        mean_temp_c=28.6,
        temp_amplitude_c=3.4,
    ),
    seasons=(
        Season("Kuruvai", 6, 10, 9, 25),
        Season("Samba", 8, 20, 1, 20),
    ),
    tenure=TenureBasis.OWNED_TITLE,
    tenure_reference="TN/RoR/THJ/2016/04412",
    farmer_name="Smallholder, 2.4 ha",
    village="Vallam",
    enrolled_on=date(2025, 6, 1),
    notes=(
        "Rice is India's largest agricultural methane source. Two crops a "
        "year here, so an AWD intervention produces evidence within months."
    ),
    # Gold Standard AWM rice: 20-100 kg CH4/ha/season baseline; delta soils
    # with heavy organic input sit high in that range. 20-50% reduction.
    baseline_ch4_kg_ha_season=78.0,
    awd_reduction=0.42,
)

NYERI = Site(
    id="KE-NYR-01",
    label="Gatugi shade-coffee block",
    country="Kenya",
    admin="Nyeri County, Central Highlands",
    lat=-0.4350,
    lon=36.9612,
    boundary=_plot(36.9612, -0.4350, width_m=232, height_m=134),
    track=TrackKind.AGROFORESTRY,
    crop="Arabica coffee (SL28, Ruiru 11) under shade",
    intervention="Shade tree establishment at 120 stems/ha, pulp composting",
    climate=Climate(
        # Nyeri: bimodal -- long rains Mar-May, short rains Oct-Dec.
        monthly_rain_mm=(41, 46, 108, 219, 131, 32, 20, 26, 33, 132, 196, 96),
        mean_temp_c=17.9,
        temp_amplitude_c=2.1,
    ),
    seasons=(
        Season("Long rains", 3, 10, 5, 31),
        Season("Short rains", 10, 8, 12, 15),
    ),
    tenure=TenureBasis.OWNED_TITLE,
    tenure_reference="KE/LR/NYERI/MUNICIPALITY/8841",
    farmer_name="Smallholder, 2.8 ha",
    village="Gatugi",
    enrolled_on=date(2025, 3, 20),
    species=("Grevillea robusta", "Cordia africana", "Macadamia tetraphylla"),
    notes=(
        "Coffee agroforestry is a removal pathway on land already under "
        "permanent crop, so tenure is cleaner than open reforestation and the "
        "shade trees earn their keep in timber and yield stability as well as "
        "carbon."
    ),
    shade_peak_height_m=13.5,
    shade_years_to_half=4.5,
)

SITES: dict[str, Site] = {s.id: s for s in (THANJAVUR, NYERI)}


def as_project(site: Site) -> Project:
    """One site as a single-plot Project, so the same engine quantifies it."""
    project = Project(
        id=site.id,
        name=f"{site.label}, {site.admin}",
        track=site.track,
        country=site.country,
        start_date=site.enrolled_on,
    )
    farmer = project.add_farmer(Farmer(
        id=f"{site.id}-F1", name=site.farmer_name, village=site.village,
        district=site.admin, state=site.admin,
        consent_on=site.enrolled_on,
        consent_reference=f"CONSENT/{site.id}/001",
    ))
    plot = project.add_plot(Plot(
        id=f"{site.id}-P1", farmer_id=farmer.id, boundary=site.boundary,
        tenure=site.tenure, tenure_reference=site.tenure_reference,
        surveyed_on=site.enrolled_on,
    ))
    practice = "awd" if site.track is TrackKind.RICE else "block_planting"
    project.enroll(Enrollment(
        plot_id=plot.id, project_id=project.id, enrolled_on=site.enrolled_on,
        practice=practice, species=list(site.species),
        stems_planted=int(site.area_ha * 120) if site.species else None,
    ))
    return project
