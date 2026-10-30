// Farm boundaries in, validated polygons out.
//
// Customers arrive with boundaries in whatever their last tool exported:
// GeoJSON from QGIS, KML from Google Earth, WKT from a database, or a column
// of GPS points a field agent walked. All of them become a GeoJSON Polygon or
// MultiPolygon in WGS84 (lon, lat), checked the same way the engine checks
// them (carbonstack.geo.validate_ring), so a farm that saves here is a farm
// the engine will accept.

import { kml as kmlToGeoJSON } from "@tmcw/togeojson";
import turfArea from "@turf/area";
import booleanValid from "@turf/boolean-valid";
import turfCentroid from "@turf/centroid";
import kinks from "@turf/kinks";
import { DOMParser } from "@xmldom/xmldom";
import type { Feature, Geometry } from "geojson";

import type { PolygonGeometry } from "@/lib/database.types";

export type ParsedBoundary = {
  geometry: PolygonGeometry;
  name?: string;
  properties?: Record<string, unknown>;
};

export type Measured = {
  area_ha: number;
  centroid_lat: number;
  centroid_lon: number;
};

/** Smallest and largest plausible farm. Matches the engine's own bounds. */
export const MIN_AREA_HA = 0.01;
export const MAX_AREA_HA = 10_000;

export class BoundaryError extends Error {}

function closeRing(ring: number[][]): number[][] {
  if (ring.length === 0) return ring;
  const [fx, fy] = ring[0];
  const [lx, ly] = ring[ring.length - 1];
  return fx === lx && fy === ly ? ring : [...ring, ring[0]];
}

function roundCoord(n: number): number {
  // ~1 cm. More digits than this are GPS noise and bloat every row.
  return Math.round(n * 1e7) / 1e7;
}

function normalise(geometry: Geometry): PolygonGeometry | null {
  if (geometry.type === "Polygon") {
    return {
      type: "Polygon",
      coordinates: geometry.coordinates.map((r) =>
        closeRing(r.map(([x, y]) => [roundCoord(x), roundCoord(y)])),
      ),
    };
  }
  if (geometry.type === "MultiPolygon") {
    const polys = geometry.coordinates.map((p) =>
      p.map((r) => closeRing(r.map(([x, y]) => [roundCoord(x), roundCoord(y)]))),
    );
    return polys.length === 1
      ? { type: "Polygon", coordinates: polys[0] }
      : { type: "MultiPolygon", coordinates: polys };
  }
  if (geometry.type === "GeometryCollection") {
    const parts = geometry.geometries.map(normalise).filter((g): g is PolygonGeometry => !!g);
    if (parts.length === 0) return null;
    if (parts.length === 1) return parts[0];
    return {
      type: "MultiPolygon",
      coordinates: parts.flatMap((g) => (g.type === "Polygon" ? [g.coordinates] : g.coordinates)),
    };
  }
  return null;
}

function featureName(props: Record<string, unknown> | null | undefined): string | undefined {
  if (!props) return undefined;
  for (const key of ["name", "Name", "NAME", "farm_name", "plot_name", "title", "id"]) {
    const v = props[key];
    if (typeof v === "string" && v.trim()) return v.trim();
    if (typeof v === "number") return String(v);
  }
  return undefined;
}

function fromFeatures(features: Feature[]): ParsedBoundary[] {
  const out: ParsedBoundary[] = [];
  for (const f of features) {
    if (!f.geometry) continue;
    const g = normalise(f.geometry);
    if (g) {
      out.push({
        geometry: g,
        name: featureName(f.properties),
        properties: (f.properties ?? undefined) as Record<string, unknown> | undefined,
      });
    }
  }
  return out;
}

export function parseGeoJSON(text: string): ParsedBoundary[] {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (e) {
    throw new BoundaryError(`not valid JSON (${(e as Error).message})`);
  }
  const obj = data as { type?: string };
  if (obj?.type === "FeatureCollection") {
    return fromFeatures((data as { features: Feature[] }).features ?? []);
  }
  if (obj?.type === "Feature") return fromFeatures([data as Feature]);
  if (typeof obj?.type === "string") {
    return fromFeatures([{ type: "Feature", properties: {}, geometry: data as Geometry }]);
  }
  throw new BoundaryError("JSON is not GeoJSON: expected a Feature, FeatureCollection or geometry");
}

export function parseKML(text: string): ParsedBoundary[] {
  const doc = new DOMParser().parseFromString(text, "text/xml");
  return fromFeatures(kmlToGeoJSON(doc).features as Feature[]);
}

const WKT_NUMBER = /-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?/g;

function wktRings(body: string): number[][][] {
  // body is "(x y, x y, ...), (x y, ...)"
  return [...body.matchAll(/\(([^()]+)\)/g)].map((m) =>
    m[1].split(",").map((pair) => {
      const nums = pair.trim().match(WKT_NUMBER)?.map(Number) ?? [];
      if (nums.length < 2) throw new BoundaryError(`bad WKT coordinate "${pair.trim()}"`);
      return [nums[0], nums[1]];
    }),
  );
}

export function parseWKT(text: string): ParsedBoundary[] {
  const t = text.trim().replace(/^SRID=\d+;/i, "");
  const kind = t.match(/^(MULTIPOLYGON|POLYGON)\s*(?:Z|M|ZM)?\s*\(/i)?.[1]?.toUpperCase();
  if (!kind) throw new BoundaryError("WKT must be a POLYGON or MULTIPOLYGON");
  const inner = t.slice(t.indexOf("(") + 1, t.lastIndexOf(")"));
  if (kind === "POLYGON") {
    return fromFeatures([
      { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: wktRings(inner) } },
    ]);
  }
  const polys = [...inner.matchAll(/\(\s*(\([^()]+\)(?:\s*,\s*\([^()]+\))*)\s*\)/g)].map((m) =>
    wktRings(m[1]),
  );
  return fromFeatures([
    { type: "Feature", properties: {}, geometry: { type: "MultiPolygon", coordinates: polys } },
  ]);
}

/**
 * Corner points typed or pasted as "lat, lon" per line -- the order a phone's
 * GPS app shows them, and the opposite of GeoJSON's. Accepts commas, spaces or
 * tabs between the two numbers.
 */
export function parseLatLonList(text: string): ParsedBoundary[] {
  const pts = text
    .split(/\r?\n|;/)
    .map((l) => l.trim())
    .filter((l) => l && !/^[a-z]/i.test(l))
    .map((l) => {
      const nums = l.match(WKT_NUMBER)?.map(Number) ?? [];
      if (nums.length < 2) throw new BoundaryError(`"${l}" is not a "lat, lon" pair`);
      const [lat, lon] = nums;
      if (Math.abs(lat) > 90) {
        throw new BoundaryError(`latitude ${lat} is out of range; enter points as "lat, lon"`);
      }
      return [lon, lat];
    });
  if (pts.length < 3) throw new BoundaryError("a boundary needs at least three corner points");
  return fromFeatures([
    { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [pts] } },
  ]);
}

/** Guess the format from the file name and content. */
export function parseBoundaryFile(text: string, filename = ""): ParsedBoundary[] {
  const name = filename.toLowerCase();
  const head = text.trimStart().slice(0, 200);
  let parsed: ParsedBoundary[];
  if (name.endsWith(".kml") || head.startsWith("<")) parsed = parseKML(text);
  else if (name.endsWith(".wkt") || /^(SRID=\d+;)?\s*(MULTI)?POLYGON/i.test(head)) parsed = parseWKT(text);
  else if (head.startsWith("{")) parsed = parseGeoJSON(text);
  else parsed = parseLatLonList(text);
  if (parsed.length === 0) throw new BoundaryError("no polygon found in the file");
  return parsed;
}

export function measure(geometry: PolygonGeometry): Measured {
  const feature: Feature = { type: "Feature", properties: {}, geometry };
  const [lon, lat] = turfCentroid(feature).geometry.coordinates;
  return {
    area_ha: Math.round((turfArea(feature) / 10_000) * 10_000) / 10_000,
    centroid_lat: Math.round(lat * 1e6) / 1e6,
    centroid_lon: Math.round(lon * 1e6) / 1e6,
  };
}

/** Problems that would stop a farm being saved or verified. Empty = fine. */
export function validate(geometry: PolygonGeometry): string[] {
  const problems: string[] = [];
  const rings = geometry.type === "Polygon" ? geometry.coordinates : geometry.coordinates.flat();
  for (const ring of rings) {
    if (ring.length < 4) {
      problems.push("a ring has fewer than three distinct corners");
      return problems;
    }
    for (const [x, y] of ring) {
      if (!Number.isFinite(x) || !Number.isFinite(y) || Math.abs(x) > 180 || Math.abs(y) > 90) {
        problems.push(`coordinate out of range: (${x}, ${y})`);
        return problems;
      }
    }
  }
  const feature: Feature = { type: "Feature", properties: {}, geometry };
  // kinks finds a ring crossing itself; booleanValid covers holes escaping
  // their shell and parts of a MultiPolygon overlapping each other.
  if (kinks(feature as Feature<PolygonGeometry>).features.length > 0 || !booleanValid(feature)) {
    problems.push("the boundary crosses itself; redraw it so edges do not overlap");
    return problems;
  }
  const { area_ha } = measure(geometry);
  if (area_ha < MIN_AREA_HA) problems.push(`implausibly small: ${area_ha.toFixed(4)} ha`);
  if (area_ha > MAX_AREA_HA) {
    problems.push(
      `implausibly large for one farm: ${area_ha.toFixed(0)} ha. Were latitude and longitude swapped?`,
    );
  }
  return problems;
}

export function bbox(geometries: PolygonGeometry[]): [number, number, number, number] | null {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  for (const g of geometries) {
    const rings = g.type === "Polygon" ? g.coordinates : g.coordinates.flat();
    for (const r of rings)
      for (const [x, y] of r) {
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      }
  }
  return Number.isFinite(minX) ? [minX, minY, maxX, maxY] : null;
}

/**
 * Share of a's bounding box covered by b's. Two farms in one organisation
 * overlapping is a double-count risk; this is the cheap first screen that
 * decides which pairs a person should look at, not proof of overlap.
 */
export function bboxOverlapShare(a: PolygonGeometry, b: PolygonGeometry): number {
  const ba = bbox([a]);
  const bb = bbox([b]);
  if (!ba || !bb) return 0;
  const ix = Math.max(0, Math.min(ba[2], bb[2]) - Math.max(ba[0], bb[0]));
  const iy = Math.max(0, Math.min(ba[3], bb[3]) - Math.max(ba[1], bb[1]));
  const areaA = (ba[2] - ba[0]) * (ba[3] - ba[1]);
  return areaA > 0 ? (ix * iy) / areaA : 0;
}
