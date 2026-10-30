// Bulk import of existing data: farms (with their farmers), practice records
// and soil lab results. Parsing and validation are pure functions so the
// browser can show a full preview -- every row, every problem -- before
// anything is written, and the server re-runs the same checks on commit.

import Papa from "papaparse";
import { z } from "zod";

import type {
  PolygonGeometry,
  RiceEcosystem,
  Season,
  Tenure,
  WaterControl,
} from "@/lib/database.types";
import { BoundaryError, measure, parseGeoJSON, parseWKT, validate, type ParsedBoundary } from "@/lib/geo";

export type ImportKind = "farms" | "practices" | "soil";

export type RowResult<T> = {
  row: number; // 1-based, as a spreadsheet shows it (header is row 1)
  value?: T;
  errors: string[];
  warnings: string[];
};

export type FarmDraft = {
  name: string;
  external_ref: string | null;
  farmer: {
    name: string;
    external_ref: string | null;
    phone: string | null;
    village: string | null;
    district: string | null;
    state: string | null;
    country: string | null;
  } | null;
  boundary: PolygonGeometry;
  area_ha: number;
  centroid_lat: number;
  centroid_lon: number;
  crop: string | null;
  practice: string | null;
  tenure: Tenure | null;
  tenure_reference: string | null;
  rice_ecosystem: RiceEcosystem | null;
  water_control: WaterControl | null;
  enrolled_on: string | null;
  seasons: Season[];
  status: "draft" | "enrolled";
};

export type PracticeDraft = {
  farm_ref: string;
  year: number;
  season: string | null;
  practice: string;
  started_on: string | null;
  ended_on: string | null;
  notes: string | null;
};

export type SoilDraft = {
  farm_ref: string;
  sampled_on: string;
  depth_top_cm: number;
  depth_bottom_cm: number;
  soc_pct: number;
  bulk_density: number | null;
  lab: string | null;
  lab_reference: string | null;
};

export const TEMPLATES: Record<ImportKind, { columns: string[]; example: string[][]; help: string }> = {
  farms: {
    columns: [
      "farm_name", "farm_ref", "farmer_name", "farmer_ref", "farmer_phone", "village", "district",
      "state", "country", "crop", "practice", "tenure", "tenure_reference", "enrolled_on",
      "rice_ecosystem", "water_control", "seasons", "boundary", "lat", "lon", "area_ha",
    ],
    example: [[
      "Murugan north", "TNJ-0001", "Murugan K", "F-0001", "+91 90000 00001", "Vallam", "Thanjavur",
      "Tamil Nadu", "India", "Paddy rice", "awd", "owned_title", "TN/RoR/THJ/2016/04412", "2025-06-01",
      "irrigated_lowland", "full", "Kuruvai:06-10/09-25;Samba:08-20/01-20",
      "POLYGON ((79.1378 10.7867, 79.139757 10.7867547, 79.1396395 10.7878395, 79.1383871 10.7878737, 79.1377413 10.7874065, 79.1378 10.7867))",
      "", "", "",
    ]],
    help:
      "One row per farm. Give the boundary as WKT or GeoJSON in `boundary`; if you only have a " +
      "point, give `lat`, `lon` and `area_ha` and the farm is imported as a draft until its " +
      "boundary is surveyed. Seasons are `Name:MM-DD/MM-DD` separated by `;`.",
  },
  practices: {
    columns: ["farm_ref", "year", "season", "practice", "started_on", "ended_on", "notes"],
    example: [["TNJ-0001", "2025", "Kuruvai", "awd", "2025-06-15", "2025-09-20", "3 dry-downs observed"]],
    help: "One row per practice per season. `farm_ref` must match a farm's reference.",
  },
  soil: {
    columns: [
      "farm_ref", "sampled_on", "depth_top_cm", "depth_bottom_cm", "soc_pct", "bulk_density", "lab",
      "lab_reference",
    ],
    example: [["TNJ-0001", "2025-05-20", "0", "30", "0.82", "1.38", "TNAU Soil Lab", "LAB-2025-0412"]],
    help: "One row per depth increment per core. SOC as % by mass; bulk density in g/cm³.",
  },
};

export function templateCsv(kind: ImportKind): string {
  const t = TEMPLATES[kind];
  return Papa.unparse({ fields: t.columns, data: t.example });
}

const TENURES: Tenure[] = [
  "owned_title", "registered_lease", "community_right", "grama_sabha_consent", "undocumented",
];
const ECOSYSTEMS: RiceEcosystem[] = ["irrigated_lowland", "rainfed", "upland", "deepwater", "unknown"];
const CONTROLS: WaterControl[] = ["full", "irrigation_only", "none", "unknown"];

const blank = (v: unknown) => v === undefined || v === null || String(v).trim() === "";
const str = (v: unknown) => (blank(v) ? null : String(v).trim());

function normaliseKey(k: string): string {
  return k.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

/** Common spellings people use in their own sheets, mapped to ours. */
const ALIASES: Record<string, string> = {
  name: "farm_name", farm: "farm_name", plot_name: "farm_name", field_name: "farm_name",
  farm_id: "farm_ref", plot_id: "farm_ref", field_id: "farm_ref", ref: "farm_ref",
  farmer: "farmer_name", farmer_id: "farmer_ref", phone: "farmer_phone", mobile: "farmer_phone",
  latitude: "lat", longitude: "lon", lng: "lon", long: "lon", hectares: "area_ha", area: "area_ha",
  wkt: "boundary", geometry: "boundary", geojson: "boundary", polygon: "boundary",
  enrolment_date: "enrolled_on", enrollment_date: "enrolled_on", date: "enrolled_on",
  soc: "soc_pct", soc_percent: "soc_pct", bd: "bulk_density",
};

export function parseCsv(text: string): { rows: Record<string, string>[]; columns: string[] } {
  const parsed = Papa.parse<Record<string, string>>(text.replace(/^﻿/, ""), {
    header: true,
    skipEmptyLines: "greedy",
    transformHeader: (h) => {
      const k = normaliseKey(h);
      return ALIASES[k] ?? k;
    },
  });
  return { rows: parsed.data, columns: parsed.meta.fields ?? [] };
}

const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, "use YYYY-MM-DD")
  .refine((s) => !Number.isNaN(Date.parse(s)), "not a real date");

function dateField(v: unknown, label: string, errors: string[]): string | null {
  const s = str(v);
  if (!s) return null;
  const r = isoDate.safeParse(s);
  if (!r.success) {
    errors.push(`${label}: ${r.error.issues[0].message} (got "${s}")`);
    return null;
  }
  return s;
}

function numberField(v: unknown, label: string, errors: string[]): number | null {
  const s = str(v);
  if (!s) return null;
  const n = Number(s.replace(/,/g, ""));
  if (!Number.isFinite(n)) {
    errors.push(`${label}: "${s}" is not a number`);
    return null;
  }
  return n;
}

function enumField<T extends string>(v: unknown, allowed: T[], label: string, errors: string[]): T | null {
  const s = str(v);
  if (!s) return null;
  const k = normaliseKey(s) as T;
  if (!allowed.includes(k)) {
    errors.push(`${label}: "${s}" is not one of ${allowed.join(", ")}`);
    return null;
  }
  return k;
}

/** "Kuruvai:06-10/09-25;Samba:08-20/01-20" */
export function parseSeasons(v: unknown, errors: string[]): Season[] {
  const s = str(v);
  if (!s) return [];
  const out: Season[] = [];
  for (const part of s.split(";").map((p) => p.trim()).filter(Boolean)) {
    const m = part.match(/^(?:([^:]+):)?\s*(\d{1,2})-(\d{1,2})\s*\/\s*(\d{1,2})-(\d{1,2})$/);
    if (!m) {
      errors.push(`seasons: "${part}" should look like Name:MM-DD/MM-DD`);
      continue;
    }
    const [, name, sm, sd, em, ed] = m;
    const season = {
      name: name?.trim() || `Season ${out.length + 1}`,
      start_month: +sm, start_day: +sd, end_month: +em, end_day: +ed,
    };
    if ([season.start_month, season.end_month].some((x) => x < 1 || x > 12) ||
        [season.start_day, season.end_day].some((x) => x < 1 || x > 31)) {
      errors.push(`seasons: "${part}" has an impossible month or day`);
      continue;
    }
    out.push(season);
  }
  return out;
}

/**
 * A square of the stated area around a point. Only for legacy records that
 * never had a boundary: the farm stays a draft, because a square is not
 * a survey and no verifier will accept one.
 */
export function squareAround(lat: number, lon: number, areaHa: number): PolygonGeometry {
  const side = Math.sqrt(areaHa * 10_000); // metres
  // On the same sphere turf measures with, so the square has the area asked.
  const metresPerDegree = (6_371_008.8 * Math.PI) / 180;
  const dLat = side / 2 / metresPerDegree;
  const dLon = side / 2 / (metresPerDegree * Math.cos((lat * Math.PI) / 180));
  const r = (n: number) => Math.round(n * 1e7) / 1e7;
  return {
    type: "Polygon",
    coordinates: [[
      [r(lon - dLon), r(lat - dLat)], [r(lon + dLon), r(lat - dLat)],
      [r(lon + dLon), r(lat + dLat)], [r(lon - dLon), r(lat + dLat)],
      [r(lon - dLon), r(lat - dLat)],
    ]],
  };
}

function boundaryFrom(row: Record<string, unknown>, errors: string[], warnings: string[]):
    { geometry: PolygonGeometry; approximate: boolean } | null {
  const raw = str(row.boundary);
  if (raw) {
    try {
      const parsed: ParsedBoundary[] = raw.startsWith("{") ? parseGeoJSON(raw) : parseWKT(raw);
      if (parsed.length !== 1) {
        errors.push(`boundary: expected one polygon, found ${parsed.length}`);
        return null;
      }
      return { geometry: parsed[0].geometry, approximate: false };
    } catch (e) {
      errors.push(`boundary: ${e instanceof BoundaryError ? e.message : String(e)}`);
      return null;
    }
  }
  const lat = numberField(row.lat, "lat", errors);
  const lon = numberField(row.lon, "lon", errors);
  const area = numberField(row.area_ha, "area_ha", errors);
  if (lat !== null && lon !== null && area !== null) {
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      errors.push(`lat/lon out of range (${lat}, ${lon})`);
      return null;
    }
    if (area <= 0) {
      errors.push("area_ha must be positive");
      return null;
    }
    warnings.push("no boundary: a square of the stated area was placed on the point; survey it before crediting");
    return { geometry: squareAround(lat, lon, area), approximate: true };
  }
  errors.push("needs a boundary (WKT or GeoJSON), or lat + lon + area_ha");
  return null;
}

export function validateFarmRow(row: Record<string, unknown>, index: number): RowResult<FarmDraft> {
  const errors: string[] = [];
  const warnings: string[] = [];
  const name = str(row.farm_name) ?? str(row.farm_ref);
  if (!name) errors.push("farm_name (or farm_ref) is required");

  const shape = boundaryFrom(row, errors, warnings);
  let measured = null;
  if (shape) {
    const problems = validate(shape.geometry);
    if (problems.length) errors.push(...problems.map((p) => `boundary: ${p}`));
    else measured = measure(shape.geometry);
  }

  const tenure = enumField(row.tenure, TENURES, "tenure", errors);
  const rice_ecosystem = enumField(row.rice_ecosystem, ECOSYSTEMS, "rice_ecosystem", errors);
  const water_control = enumField(row.water_control, CONTROLS, "water_control", errors);
  const enrolled_on = dateField(row.enrolled_on, "enrolled_on", errors);
  const seasons = parseSeasons(row.seasons, errors);

  if (!tenure) warnings.push("no tenure basis: the farm cannot be credited until one is recorded");
  else if (tenure !== "undocumented" && !str(row.tenure_reference)) {
    warnings.push("tenure has no reference document: credits stay blocked until it is attached");
  }

  const farmerName = str(row.farmer_name);
  if (!farmerName) warnings.push("no farmer named: payments cannot be raised for this farm");

  if (errors.length || !shape || !measured || !name) {
    return { row: index + 2, errors, warnings };
  }
  return {
    row: index + 2,
    errors,
    warnings,
    value: {
      name,
      external_ref: str(row.farm_ref),
      farmer: farmerName
        ? {
            name: farmerName,
            external_ref: str(row.farmer_ref),
            phone: str(row.farmer_phone),
            village: str(row.village),
            district: str(row.district),
            state: str(row.state),
            country: str(row.country),
          }
        : null,
      boundary: shape.geometry,
      ...measured,
      crop: str(row.crop),
      practice: str(row.practice),
      tenure,
      tenure_reference: str(row.tenure_reference),
      rice_ecosystem,
      water_control,
      enrolled_on,
      seasons,
      status: shape.approximate ? "draft" : "enrolled",
    },
  };
}

export function validatePracticeRow(row: Record<string, unknown>, index: number): RowResult<PracticeDraft> {
  const errors: string[] = [];
  const farm_ref = str(row.farm_ref);
  if (!farm_ref) errors.push("farm_ref is required");
  const year = numberField(row.year, "year", errors);
  if (year !== null && (!Number.isInteger(year) || year < 1990 || year > 2100)) {
    errors.push(`year: ${year} is not a plausible year`);
  }
  const practice = str(row.practice);
  if (!practice) errors.push("practice is required");
  const started_on = dateField(row.started_on, "started_on", errors);
  const ended_on = dateField(row.ended_on, "ended_on", errors);
  if (started_on && ended_on && ended_on < started_on) errors.push("ended_on is before started_on");
  if (errors.length || !farm_ref || year === null || !practice) return { row: index + 2, errors, warnings: [] };
  return {
    row: index + 2, errors, warnings: [],
    value: { farm_ref, year, season: str(row.season), practice, started_on, ended_on, notes: str(row.notes) },
  };
}

export function validateSoilRow(row: Record<string, unknown>, index: number): RowResult<SoilDraft> {
  const errors: string[] = [];
  const warnings: string[] = [];
  const farm_ref = str(row.farm_ref);
  if (!farm_ref) errors.push("farm_ref is required");
  const sampled_on = dateField(row.sampled_on, "sampled_on", errors);
  if (!str(row.sampled_on)) errors.push("sampled_on is required");
  const top = numberField(row.depth_top_cm, "depth_top_cm", errors);
  const bottom = numberField(row.depth_bottom_cm, "depth_bottom_cm", errors);
  const soc = numberField(row.soc_pct, "soc_pct", errors);
  const bd = numberField(row.bulk_density, "bulk_density", errors);
  if (top === null || bottom === null) errors.push("depth_top_cm and depth_bottom_cm are required");
  else if (bottom <= top) errors.push("depth_bottom_cm must be below depth_top_cm");
  if (soc === null) errors.push("soc_pct is required");
  else if (soc < 0 || soc >= 60) errors.push(`soc_pct ${soc} is outside 0-60 %`);
  else if (soc > 10) warnings.push(`soc_pct ${soc} is high for mineral soil; check it is % and not g/kg`);
  if (bd !== null && (bd <= 0 || bd >= 3)) errors.push(`bulk_density ${bd} is outside 0-3 g/cm³`);
  if (bd === null) warnings.push("no bulk density: stocks cannot be computed on equivalent soil mass");
  if (errors.length || !farm_ref || !sampled_on || top === null || bottom === null || soc === null) {
    return { row: index + 2, errors, warnings };
  }
  return {
    row: index + 2, errors, warnings,
    value: {
      farm_ref, sampled_on, depth_top_cm: top, depth_bottom_cm: bottom, soc_pct: soc,
      bulk_density: bd, lab: str(row.lab), lab_reference: str(row.lab_reference),
    },
  };
}

export type ImportPreview<T> = {
  kind: ImportKind;
  columns: string[];
  results: RowResult<T>[];
  ok: number;
  failed: number;
  warned: number;
};

function summarise<T>(kind: ImportKind, columns: string[], results: RowResult<T>[]): ImportPreview<T> {
  return {
    kind,
    columns,
    results,
    ok: results.filter((r) => r.value).length,
    failed: results.filter((r) => !r.value).length,
    warned: results.filter((r) => r.value && r.warnings.length).length,
  };
}

/** Duplicate references inside one file are almost always a copy-paste slip. */
function flagDuplicateRefs<T extends { external_ref?: string | null }>(results: RowResult<T>[]) {
  const seen = new Map<string, number>();
  for (const r of results) {
    const ref = r.value?.external_ref;
    if (!ref) continue;
    if (seen.has(ref)) {
      r.errors.push(`farm_ref "${ref}" repeats row ${seen.get(ref)}`);
      r.value = undefined;
    } else seen.set(ref, r.row);
  }
}

export function previewFarms(text: string): ImportPreview<FarmDraft> {
  const { rows, columns } = parseCsv(text);
  const results = rows.map(validateFarmRow);
  flagDuplicateRefs(results);
  return summarise("farms", columns, results);
}

/** A GeoJSON or KML file is a farm import whose rows are its features. */
export function previewFarmFeatures(features: ParsedBoundary[]): ImportPreview<FarmDraft> {
  const results = features.map((f, i) => {
    const props = Object.fromEntries(
      Object.entries(f.properties ?? {}).map(([k, v]) => {
        const key = normaliseKey(k);
        return [ALIASES[key] ?? key, v];
      }),
    );
    return validateFarmRow(
      { ...props, farm_name: props.farm_name ?? f.name ?? `Farm ${i + 1}`, boundary: JSON.stringify(f.geometry) },
      i,
    );
  });
  flagDuplicateRefs(results);
  return summarise("farms", Object.keys(features[0]?.properties ?? {}), results);
}

export function previewPractices(text: string): ImportPreview<PracticeDraft> {
  const { rows, columns } = parseCsv(text);
  return summarise("practices", columns, rows.map(validatePracticeRow));
}

export function previewSoil(text: string): ImportPreview<SoilDraft> {
  const { rows, columns } = parseCsv(text);
  return summarise("soil", columns, rows.map(validateSoilRow));
}
