"""Geometry, without a geospatial stack.

Plot boundaries arrive as WGS84 rings from a field app. We need area, centroid
and bounding box, and we need them to agree with what a verifier computes in
QGIS. That is a small enough job to do exactly, and doing it here keeps the
core installable anywhere -- which matters when the same code has to run in a
notebook, a batch job and a field laptop.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8  # IUGG mean radius
Ring = list[tuple[float, float]]  # [(lon, lat), ...]


def _closed(ring: Ring) -> Ring:
    if len(ring) >= 3 and ring[0] != ring[-1]:
        return [*ring, ring[0]]
    return list(ring)


def area_ha(ring: Ring) -> float:
    """Geodesic area of a WGS84 ring, in hectares.

    Uses the spherical excess formula rather than projecting, so it stays
    accurate for plots anywhere on earth and for rings that cross a UTM zone
    boundary -- both of which happen in real enrolment data.
    """
    pts = _closed(ring)
    if len(pts) < 4:
        return 0.0

    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(pts, pts[1:]):
        d_lon = math.radians(lon2 - lon1)
        total += d_lon * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    area_m2 = abs(total * EARTH_RADIUS_M * EARTH_RADIUS_M / 2.0)
    return area_m2 / 10_000.0


def centroid(ring: Ring) -> tuple[float, float]:
    """Area-weighted centroid (lon, lat) of a small ring.

    Planar within the ring, which is right for plot-scale polygons and wrong
    for continent-scale ones. Plots are plot-scale.
    """
    pts = _closed(ring)
    if len(pts) < 4:
        n = max(len(ring), 1)
        return (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n)

    a2 = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        cross = x1 * y2 - x2 * y1
        a2 += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if a2 == 0:
        n = len(pts) - 1
        return (sum(p[0] for p in pts[:-1]) / n, sum(p[1] for p in pts[:-1]) / n)
    return (cx / (3 * a2), cy / (3 * a2))


def bbox(ring: Ring) -> tuple[float, float, float, float]:
    """(min_lon, min_lat, max_lon, max_lat)."""
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return (min(lons), min(lats), max(lons), max(lats))


def validate_ring(ring: Ring) -> list[str]:
    """Boundary problems that would fail validation, found at enrolment time.

    Catching these when the enumerator is still standing in the field costs
    nothing. Catching them at verification costs a season.
    """
    problems: list[str] = []
    if len(_closed(ring)) < 4:
        problems.append("ring has fewer than three distinct vertices")
        return problems

    for lon, lat in ring:
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            problems.append(f"vertex out of range: ({lon}, {lat})")
            break

    a = area_ha(ring)
    if a <= 0:
        problems.append("ring encloses no area")
    elif a < 0.01:
        problems.append(f"implausibly small plot: {a:.4f} ha")
    elif a > 10_000:
        problems.append(f"implausibly large plot: {a:,.0f} ha")

    if _self_intersects(_closed(ring)):
        problems.append("boundary self-intersects")

    return problems


def _self_intersects(pts: Ring) -> bool:
    edges = list(zip(pts, pts[1:]))
    n = len(edges)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # shared closing vertex
            if _crosses(edges[i], edges[j]):
                return True
    return False


def _crosses(e1, e2) -> bool:
    (p1, p2), (p3, p4) = e1, e2

    def orient(a, b, c) -> int:
        v = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
        return (v > 0) - (v < 0)

    o1, o2 = orient(p1, p2, p3), orient(p1, p2, p4)
    o3, o4 = orient(p3, p4, p1), orient(p3, p4, p2)
    return o1 != o2 and o3 != o4
