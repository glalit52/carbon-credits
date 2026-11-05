import type { CheckInput, CheckResult } from "./checker-engine";
import { evaluateField, POPULAR_PRESETS, synthesizeBoundary } from "./checker-engine";

export interface SavedFieldRecord {
  id: string;
  name: string;
  input: CheckInput;
  result: CheckResult;
  createdAt: string;
  updatedAt: string;
  tags?: string[];
  starred?: boolean;
}

const STORAGE_KEY = "carbonstack_saved_fields_v1";

/** Initial seed fields so a user instantly has realistic, working saved fields to explore. */
export function getDefaultSeedFields(): SavedFieldRecord[] {
  const p1 = POPULAR_PRESETS[0]; // Thanjavur
  const p2 = POPULAR_PRESETS[1]; // Nyeri
  const p3 = POPULAR_PRESETS[2]; // Punjab

  const boundary1 = synthesizeBoundary(p1.lat, p1.lon, p1.area_ha);
  const boundary2 = synthesizeBoundary(p2.lat, p2.lon, p2.area_ha);
  const boundary3 = synthesizeBoundary(p3.lat, p3.lon, p3.area_ha);

  const in1: CheckInput = {
    name: "Murugan — North Kaveri Field",
    lat: p1.lat,
    lon: p1.lon,
    area_ha: p1.area_ha,
    boundary: boundary1,
    pathway: p1.pathway,
    crop: p1.crop,
    practice: p1.practice,
    tenure: "owned_title",
    tenure_reference: "PATTA-TNJ-2024-0042",
    farmer_name: "Murugan Swaminathan",
    rice_ecosystem: p1.rice_ecosystem,
    water_control: p1.water_control,
    seasons_per_year: p1.seasons_per_year,
    season_days: p1.season_days,
    measurement_tier: 2,
    carbon_price_usd: 15.0,
    farmer_share_pct: 60.0,
    monitoring_cost_per_ha: 6.2,
  };

  const in2: CheckInput = {
    name: "Gatugi Coffee Agroforestry Stand",
    lat: p2.lat,
    lon: p2.lon,
    area_ha: p2.area_ha,
    boundary: boundary2,
    pathway: p2.pathway,
    crop: p2.crop,
    practice: p2.practice,
    tenure: "owned_title",
    tenure_reference: "NYERI-TITLE-29184",
    farmer_name: "Grace Wanjiku Kamau",
    stems_planted_per_ha: p2.stems_planted_per_ha,
    tree_species: p2.tree_species,
    seasons_per_year: 1,
    season_days: 365,
    measurement_tier: 1,
    carbon_price_usd: 18.0,
    farmer_share_pct: 65.0,
    monitoring_cost_per_ha: 6.2,
  };

  const in3: CheckInput = {
    name: "Ludhiana Basmati AWD Pilot",
    lat: p3.lat,
    lon: p3.lon,
    area_ha: p3.area_ha,
    boundary: boundary3,
    pathway: p3.pathway,
    crop: p3.crop,
    practice: p3.practice,
    tenure: "registered_lease",
    tenure_reference: "PB-REG-LEASE-8812",
    farmer_name: "Harpreet Singh Sandhu",
    rice_ecosystem: p3.rice_ecosystem,
    water_control: p3.water_control,
    seasons_per_year: p3.seasons_per_year,
    season_days: p3.season_days,
    measurement_tier: 3, // Flux tower calibrated
    carbon_price_usd: 15.0,
    farmer_share_pct: 60.0,
    monitoring_cost_per_ha: 6.2,
  };

  return [
    {
      id: "seed-thanjavur-1",
      name: in1.name,
      input: in1,
      result: evaluateField(in1),
      createdAt: "2026-10-15T10:00:00Z",
      updatedAt: "2026-10-15T10:00:00Z",
      tags: ["Pilot", "Kaveri Delta", "AWD"],
      starred: true,
    },
    {
      id: "seed-nyeri-2",
      name: in2.name,
      input: in2,
      result: evaluateField(in2),
      createdAt: "2026-10-18T14:30:00Z",
      updatedAt: "2026-10-18T14:30:00Z",
      tags: ["Agroforestry", "Coffee", "Highland"],
      starred: true,
    },
    {
      id: "seed-ludhiana-3",
      name: in3.name,
      input: in3,
      result: evaluateField(in3),
      createdAt: "2026-10-22T08:15:00Z",
      updatedAt: "2026-10-22T08:15:00Z",
      tags: ["Punjab", "Tier 3 Flux Tower", "Basmati"],
      starred: false,
    },
  ];
}

/** Retrieve all saved fields from localStorage, falling back to initial seed data. */
export function getSavedFields(): SavedFieldRecord[] {
  if (typeof window === "undefined") return getDefaultSeedFields();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      const initial = getDefaultSeedFields();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(initial));
      return initial;
    }
    const parsed = JSON.parse(raw) as SavedFieldRecord[];
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : getDefaultSeedFields();
  } catch {
    return getDefaultSeedFields();
  }
}

/** Save a new field or location. */
export function saveField(input: CheckInput, tags: string[] = []): SavedFieldRecord {
  const fields = getSavedFields();
  const id = `fld_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
  const now = new Date().toISOString();
  const result = evaluateField(input);

  const record: SavedFieldRecord = {
    id,
    name: input.name.trim() || `Field at ${input.lat.toFixed(4)}, ${input.lon.toFixed(4)}`,
    input: { ...input, name: input.name.trim() || `Field at ${input.lat.toFixed(4)}, ${input.lon.toFixed(4)}` },
    result,
    createdAt: now,
    updatedAt: now,
    tags,
    starred: false,
  };

  const updated = [record, ...fields];
  if (typeof window !== "undefined") {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  }
  return record;
}

/** Update an existing field. */
export function updateField(id: string, updates: Partial<CheckInput>, tags?: string[]): SavedFieldRecord | null {
  const fields = getSavedFields();
  const idx = fields.findIndex((f) => f.id === id);
  if (idx === -1) return null;

  const existing = fields[idx];
  const mergedInput: CheckInput = { ...existing.input, ...updates };
  const updatedResult = evaluateField(mergedInput);

  const updatedRecord: SavedFieldRecord = {
    ...existing,
    name: mergedInput.name,
    input: mergedInput,
    result: updatedResult,
    updatedAt: new Date().toISOString(),
    tags: tags ?? existing.tags,
  };

  fields[idx] = updatedRecord;
  if (typeof window !== "undefined") {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(fields));
  }
  return updatedRecord;
}

/** Delete a field by ID. */
export function deleteField(id: string): boolean {
  const fields = getSavedFields();
  const filtered = fields.filter((f) => f.id !== id);
  if (filtered.length === fields.length) return false;
  if (typeof window !== "undefined") {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
  }
  return true;
}

/** Toggle starred status. */
export function toggleStarField(id: string): boolean {
  const fields = getSavedFields();
  const record = fields.find((f) => f.id === id);
  if (!record) return false;
  record.starred = !record.starred;
  record.updatedAt = new Date().toISOString();
  if (typeof window !== "undefined") {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(fields));
  }
  return !!record.starred;
}

/** Export all saved fields as standard GeoJSON FeatureCollection. */
export function exportFieldsGeoJSON(): string {
  const fields = getSavedFields();
  const features = fields.map((f) => {
    const boundary = f.input.boundary ?? synthesizeBoundary(f.input.lat, f.input.lon, f.input.area_ha);
    return {
      type: "Feature",
      id: f.id,
      properties: {
        id: f.id,
        name: f.name,
        farmer_name: f.input.farmer_name,
        pathway: f.input.pathway,
        crop: f.input.crop,
        practice: f.input.practice,
        area_ha: f.input.area_ha,
        tenure: f.input.tenure,
        tenure_reference: f.input.tenure_reference,
        eligibility: f.result.eligibility,
        methodology: f.result.methodology,
        gross_tco2e_yr: f.result.grossAbatementTonnesYear,
        net_tco2e_yr: f.result.netCreditsTonnesYear,
        annual_revenue_usd: f.result.annualGrossRevenueUSD,
        annual_farmer_payout_usd: f.result.annualFarmerPayoutUSD,
        created_at: f.createdAt,
      },
      geometry: boundary,
    };
  });

  return JSON.stringify({ type: "FeatureCollection", features }, null, 2);
}

/** Export single field as standard Google Earth KML polygon. */
export function exportFieldKML(record: SavedFieldRecord): string {
  const boundary = record.input.boundary ?? synthesizeBoundary(record.input.lat, record.input.lon, record.input.area_ha);
  const rings = boundary.type === "Polygon" ? boundary.coordinates : boundary.coordinates[0];
  const outerRing = rings[0];
  const coordString = outerRing.map(([lon, lat]) => `${lon},${lat},0`).join(" ");

  return `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>${record.name}</name>
    <description>
      <![CDATA[
        <b>Pathway:</b> ${record.input.pathway}<br/>
        <b>Area:</b> ${record.input.area_ha.toFixed(2)} ha<br/>
        <b>Net Credits:</b> ${record.result.netCreditsTonnesYear} tCO2e/yr (${record.result.methodology})<br/>
        <b>Annual Farmer Payout:</b> $${record.result.annualFarmerPayoutUSD.toLocaleString()}/yr<br/>
        <b>Status:</b> ${record.result.eligibility}
      ]]>
    </description>
    <Style id="farmPoly">
      <LineStyle>
        <color>ff49d18a</color>
        <width>2.5</width>
      </LineStyle>
      <PolyStyle>
        <color>4d49d18a</color>
      </PolyStyle>
    </Style>
    <Placemark>
      <name>${record.name}</name>
      <styleUrl>#farmPoly</styleUrl>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>${coordString}</coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>`;
}

/** Export all fields as CSV table. */
export function exportFieldsCSV(): string {
  const fields = getSavedFields();
  const headers = [
    "Field ID",
    "Name",
    "Farmer",
    "Latitude",
    "Longitude",
    "Area (ha)",
    "Pathway",
    "Crop",
    "Practice",
    "Tenure",
    "Tenure Ref",
    "Methodology",
    "Eligibility",
    "Gross tCO2e/yr",
    "Buffer Deduction %",
    "Uncertainty Deduction %",
    "Net Credits tCO2e/yr",
    "Annual Revenue (USD)",
    "Farmer Payout (USD)",
    "Monitoring Cost (USD)",
    "Net Margin (USD)",
    "Created Date",
  ];

  const rows = fields.map((f) => [
    `"${f.id}"`,
    `"${f.name.replace(/"/g, '""')}"`,
    `"${(f.input.farmer_name || "").replace(/"/g, '""')}"`,
    f.input.lat.toFixed(6),
    f.input.lon.toFixed(6),
    f.input.area_ha.toFixed(2),
    f.input.pathway,
    `"${(f.input.crop || "").replace(/"/g, '""')}"`,
    f.input.practice,
    f.input.tenure,
    `"${(f.input.tenure_reference || "").replace(/"/g, '""')}"`,
    f.result.methodology,
    f.result.eligibility,
    f.result.grossAbatementTonnesYear.toFixed(2),
    f.result.bufferDeductionPct,
    f.result.uncertaintyDeductionPct,
    f.result.netCreditsTonnesYear.toFixed(2),
    f.result.annualGrossRevenueUSD,
    f.result.annualFarmerPayoutUSD,
    f.result.annualMonitoringCostUSD,
    f.result.annualNetMarginUSD,
    `"${f.createdAt}"`,
  ]);

  return [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
}

