import { describe, expect, it } from "vitest";

import {
  BoundaryError,
  bboxOverlapShare,
  measure,
  parseBoundaryFile,
  parseLatLonList,
  parseWKT,
  validate,
} from "./geo";

// The Vallam pilot plot (sites.py THANJAVUR), ~2.49 ha.
const VALLAM = [
  [79.1378, 10.7867],
  [79.139757, 10.7867547],
  [79.1396395, 10.7878395],
  [79.1383871, 10.7878737],
  [79.1377413, 10.7874065],
  [79.1378, 10.7867],
];

describe("parsing", () => {
  it("reads a GeoJSON FeatureCollection and keeps feature names", () => {
    const text = JSON.stringify({
      type: "FeatureCollection",
      features: [
        { type: "Feature", properties: { name: "North plot" }, geometry: { type: "Polygon", coordinates: [VALLAM] } },
        { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [0, 0] } },
      ],
    });
    const parsed = parseBoundaryFile(text, "plots.geojson");
    expect(parsed).toHaveLength(1);
    expect(parsed[0].name).toBe("North plot");
    expect(parsed[0].geometry.type).toBe("Polygon");
  });

  it("closes an open ring", () => {
    const open = VALLAM.slice(0, -1);
    const [p] = parseBoundaryFile(JSON.stringify({ type: "Polygon", coordinates: [open] }));
    const ring = (p.geometry.coordinates as number[][][])[0];
    expect(ring[0]).toEqual(ring[ring.length - 1]);
  });

  it("reads KML from Google Earth", () => {
    const coords = VALLAM.map(([x, y]) => `${x},${y},0`).join(" ");
    const kml = `<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>
      <Placemark><name>Murugan field</name><Polygon><outerBoundaryIs><LinearRing>
      <coordinates>${coords}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
      </Document></kml>`;
    const [p] = parseBoundaryFile(kml, "field.kml");
    expect(p.name).toBe("Murugan field");
    expect(measure(p.geometry).area_ha).toBeCloseTo(2.49, 1);
  });

  it("reads WKT polygons and multipolygons", () => {
    const ring = VALLAM.map(([x, y]) => `${x} ${y}`).join(", ");
    expect(parseWKT(`POLYGON ((${ring}))`)[0].geometry.type).toBe("Polygon");
    const multi = parseWKT(`SRID=4326;MULTIPOLYGON (((${ring})), ((${ring})))`)[0];
    expect(multi.geometry.type).toBe("MultiPolygon");
  });

  it("reads walked GPS points in lat, lon order", () => {
    const text = VALLAM.slice(0, -1)
      .map(([lon, lat]) => `${lat}, ${lon}`)
      .join("\n");
    const [p] = parseLatLonList("lat, lon\n" + text);
    expect(measure(p.geometry).centroid_lon).toBeCloseTo(79.1387, 3);
    expect(measure(p.geometry).centroid_lat).toBeCloseTo(10.7873, 3);
  });

  it("refuses lon, lat pasted into the lat, lon box when the longitude cannot be a latitude", () => {
    // Luzon: lon 120.9 is out of range as a latitude, so the swap is caught.
    expect(() => parseLatLonList("120.9, 14.6\n121.0, 14.6\n121.0, 14.7")).toThrow(/latitude 120.9/);
  });

  it("explains what it could not read", () => {
    expect(() => parseBoundaryFile("{not json")).toThrow(BoundaryError);
    expect(() => parseBoundaryFile("10.1, 79.1\n10.2, 79.2")).toThrow(/three corner points/);
  });
});

describe("measuring and validating", () => {
  it("agrees with the engine's area for the Vallam plot", () => {
    // carbonstack.geo.area_ha gives 2.4918 ha for this ring.
    expect(measure({ type: "Polygon", coordinates: [VALLAM] }).area_ha).toBeCloseTo(2.4918, 2);
  });

  it("accepts a clean farm", () => {
    expect(validate({ type: "Polygon", coordinates: [VALLAM] })).toEqual([]);
  });

  it("rejects a bow-tie", () => {
    const bowtie = [
      [79.0, 10.0],
      [79.01, 10.01],
      [79.01, 10.0],
      [79.0, 10.01],
      [79.0, 10.0],
    ];
    expect(validate({ type: "Polygon", coordinates: [bowtie] }).join()).toMatch(/crosses itself/);
  });

  it("flags swapped coordinates as implausibly large", () => {
    const big = [
      [10, 70],
      [11, 70],
      [11, 71],
      [10, 71],
      [10, 70],
    ];
    expect(validate({ type: "Polygon", coordinates: [big] }).join()).toMatch(/swapped/);
  });

  it("flags slivers", () => {
    const tiny = [
      [79, 10],
      [79.00001, 10],
      [79.00001, 10.00001],
      [79, 10],
    ];
    expect(validate({ type: "Polygon", coordinates: [tiny] }).join()).toMatch(/small/);
  });

  it("screens overlapping farms by bounding box", () => {
    const a = { type: "Polygon" as const, coordinates: [VALLAM] };
    const far = {
      type: "Polygon" as const,
      coordinates: [VALLAM.map(([x, y]) => [x + 1, y])],
    };
    expect(bboxOverlapShare(a, a)).toBeCloseTo(1);
    expect(bboxOverlapShare(a, far)).toBe(0);
  });
});
