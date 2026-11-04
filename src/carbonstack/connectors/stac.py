"""What imagery actually exists over a plot, before anything is read from it.

The rice pathway assumes a Sentinel-1 pass every six days and the coffee
pathway a usable Sentinel-2 pass every few weeks. Both are assumptions until
the catalogue says otherwise, and they have been wrong before: Sentinel-1B
failed in December 2021 and for three years the real revisit over most of
India was twelve days, which halves the evidence a season produces. A
project document that quoted six would not have been lying, only stale.

So this module asks a STAC catalogue -- the standard search API that Element
84's Earth Search and the Copernicus Data Space both expose -- which scenes
intersect a plot's bounding box in a window, and turns the answer into the
two numbers a monitoring plan is judged on: how many acquisitions were
**usable**, and what was the **longest gap** between them. The longest gap is
the one that matters for AWD, because a dry-down shorter than the gap can
happen and be invisible.

It reads metadata only. No pixels are downloaded here; that is the job of
the processing pipeline, which this tells what to fetch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .base import ConnectorUnavailable, Snapshot, Transport

CATALOGUES = {
    "earth-search": "https://earth-search.aws.element84.com/v1/search",
    "cdse": "https://stac.dataspace.copernicus.eu/v1/search",
}

COLLECTIONS = {
    "s2": "sentinel-2-l2a",
    "s1": "sentinel-1-grd",
}

DEFAULT_MAX_CLOUD = 30.0
"""Scene-level cloud cover above which an optical pass is not counted as
usable. Scene-level is generous -- the cloud can be anywhere in a 110 km
tile -- so this overstates usable passes for a 2 ha plot, never understates
them. Plot-level masking happens downstream."""


@dataclass(frozen=True)
class Scene:
    id: str
    collection: str
    acquired: datetime
    cloud_cover: float | None
    platform: str
    relative_orbit: int | None = None
    orbit_state: str | None = None

    @property
    def day(self) -> date:
        return self.acquired.date()


@dataclass
class Coverage:
    """How well a window was observed."""

    collection: str
    start: date
    end: date
    scenes: list[Scene]
    max_cloud: float | None
    provenance: list[dict] = field(default_factory=list)

    @property
    def acquisition_days(self) -> list[date]:
        """Distinct days with a pass. Two tiles on one day are one look."""
        return sorted({s.day for s in self.scenes})

    @property
    def usable_days(self) -> list[date]:
        if self.max_cloud is None:
            return self.acquisition_days
        return sorted({s.day for s in self.scenes
                       if s.cloud_cover is not None and s.cloud_cover <= self.max_cloud})

    @property
    def platforms(self) -> list[str]:
        return sorted({s.platform for s in self.scenes if s.platform})

    def gaps_days(self) -> list[int]:
        """Gaps between usable looks, including from the window's edges.

        Edges count: a season whose first usable pass is three weeks in has a
        three-week blind spot at transplanting, which is when AWD starts.
        """
        days = self.usable_days
        if not days:
            return [(self.end - self.start).days]
        points = [self.start] + days + [self.end]
        return [(b - a).days for a, b in zip(points, points[1:])]

    @property
    def max_gap_days(self) -> int:
        return max(self.gaps_days())

    @property
    def median_revisit_days(self) -> float | None:
        days = self.usable_days
        if len(days) < 2:
            return None
        gaps = sorted((b - a).days for a, b in zip(days, days[1:]))
        mid = len(gaps) // 2
        return float(gaps[mid]) if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2

    def can_resolve(self, event_days: int) -> bool:
        """Could an event this long fall entirely between two looks?"""
        return self.max_gap_days <= event_days

    def to_dict(self) -> dict:
        return {
            "collection": self.collection,
            "start": self.start.isoformat(), "end": self.end.isoformat(),
            "scenes": len(self.scenes),
            "acquisition_days": len(self.acquisition_days),
            "usable_days": len(self.usable_days),
            "max_cloud": self.max_cloud,
            "median_revisit_days": self.median_revisit_days,
            "max_gap_days": self.max_gap_days,
            "platforms": self.platforms,
            "provenance": self.provenance,
        }


def bbox_of(ring: list[tuple[float, float]], pad_deg: float = 0.0) -> list[float]:
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return [min(lons) - pad_deg, min(lats) - pad_deg,
            max(lons) + pad_deg, max(lats) + pad_deg]


def _parse_dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def parse_features(snap: Snapshot, collection: str) -> tuple[list[Scene], dict | None]:
    """Scenes on this page, and the request for the next page if there is one."""
    data = snap.json()
    if data.get("type") != "FeatureCollection":
        raise ConnectorUnavailable(
            "stac", f"expected a FeatureCollection, got {data.get('type')!r}",
            "check the catalogue URL and collection id")
    scenes = []
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        when = props.get("datetime") or props.get("start_datetime")
        if not when:
            continue
        scenes.append(Scene(
            id=feat.get("id", ""),
            collection=feat.get("collection", collection),
            acquired=_parse_dt(when),
            cloud_cover=props.get("eo:cloud_cover"),
            platform=props.get("platform", ""),
            relative_orbit=props.get("sat:relative_orbit"),
            orbit_state=props.get("sat:orbit_state"),
        ))
    nxt = None
    for link in data.get("links", []):
        if link.get("rel") == "next":
            nxt = link
            break
    return scenes, nxt


def search(transport: Transport, *, bbox: list[float], start: date, end: date,
           sensor: str = "s1", catalogue: str = "earth-search",
           max_cloud: float | None = None, max_pages: int = 20,
           page_size: int = 100) -> Coverage:
    """All scenes over `bbox` between `start` and `end`, paging to the end.

    Stops after `max_pages` and **says so** rather than returning a truncated
    list as if it were complete, because a coverage report built on page one
    of five would understate every gap.
    """
    if sensor not in COLLECTIONS:
        raise ValueError(f"sensor must be one of {sorted(COLLECTIONS)}")
    url = CATALOGUES.get(catalogue, catalogue)
    collection = COLLECTIONS[sensor]
    body: dict = {
        "collections": [collection],
        "bbox": [round(v, 6) for v in bbox],
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "limit": page_size,
    }
    if sensor == "s2" and max_cloud is None:
        max_cloud = DEFAULT_MAX_CLOUD

    scenes: list[Scene] = []
    provenance = []
    for _ in range(max_pages):
        snap = transport.fetch("stac", url, None, body=body)
        provenance.append(snap.provenance() | {"body": body})
        page, nxt = parse_features(snap, collection)
        scenes.extend(page)
        if not nxt:
            break
        if nxt.get("body"):
            body = {**body, **nxt["body"]}
        else:
            raise ConnectorUnavailable(
                "stac", "catalogue paginates by GET link, which this client does not follow",
                "reduce the window or raise the page size")
    else:
        raise ConnectorUnavailable(
            "stac", f"more than {max_pages} pages of results",
            "narrow the window; a partial scene list would understate every gap")
    return Coverage(collection, start, end, scenes,
                    max_cloud if sensor == "s2" else None, provenance)
