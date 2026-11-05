import { describe, expect, it } from "vitest";

import {
  evaluateField,
  estimateClimate,
  simulateSentinelRadarPasses,
  synthesizeBoundary,
  type CheckInput,
} from "./checker-engine";
import {
  exportFieldsCSV,
  exportFieldsGeoJSON,
  getSavedFields,
} from "./saved-locations-store";

describe("checker-engine", () => {
  it("synthesizes a valid polygon boundary from coordinates and area", () => {
    const poly = synthesizeBoundary(10.787, 79.138, 2.5);
    expect(poly.type).toBe("Polygon");
    expect(poly.coordinates[0].length).toBe(5);
    // Closed ring
    expect(poly.coordinates[0][0]).toEqual(poly.coordinates[0][4]);
  });

  it("evaluates a rice farm under VM0051 with AWD practice", () => {
    const input: CheckInput = {
      name: "Test Kaveri Rice Field",
      lat: 10.787,
      lon: 79.138,
      area_ha: 3.0,
      pathway: "rice",
      crop: "Paddy",
      practice: "awd",
      tenure: "owned_title",
      tenure_reference: "PATTA-1234",
      rice_ecosystem: "irrigated_lowland",
      water_control: "full",
      seasons_per_year: 2,
      season_days: 110,
      measurement_tier: 2,
      carbon_price_usd: 15.0,
      farmer_share_pct: 60.0,
    };

    const res = evaluateField(input);
    expect(res.eligibility).toBe("PASS");
    expect(res.methodology).toBe("VM0051");
    expect(res.grossAbatementTonnesYear).toBeGreaterThan(0);
    expect(res.netCreditsTonnesYear).toBeGreaterThan(0);
    expect(res.bufferDeductionPct).toBe(0); // VM0051 avoided methane has 0% buffer pool
    expect(res.uncertaintyDeductionPct).toBe(15); // Tier 2 has 15% uncertainty deduction
    expect(res.annualGrossRevenueUSD).toBeGreaterThan(0);
    expect(res.annualFarmerPayoutUSD).toBe(Math.round(res.annualGrossRevenueUSD * 0.6));
    expect(res.projections5Year.length).toBe(5);
    expect(res.derivationSteps.length).toBeGreaterThan(3);
  });

  it("blocks rice without drainage control when AWD is claimed", () => {
    const input: CheckInput = {
      name: "No Drainage Rice Field",
      lat: 10.787,
      lon: 79.138,
      area_ha: 2.0,
      pathway: "rice",
      practice: "awd",
      tenure: "owned_title",
      water_control: "none", // Cannot do AWD
    };

    const res = evaluateField(input);
    expect(res.eligibility).toBe("BLOCKED");
    expect(res.blockers.some((b) => b.includes("water control is 'none'"))).toBe(true);
  });

  it("blocks undocumented tenure per VCS standard", () => {
    const input: CheckInput = {
      name: "Undocumented Plot",
      lat: 10.787,
      lon: 79.138,
      area_ha: 1.5,
      pathway: "rice",
      practice: "awd",
      tenure: "undocumented",
      water_control: "full",
      rice_ecosystem: "irrigated_lowland",
    };

    const res = evaluateField(input);
    expect(res.eligibility).toBe("BLOCKED");
    expect(res.blockers.some((b) => b.includes("undocumented"))).toBe(true);
  });

  it("evaluates agroforestry under VM0047 with buffer pool deduction", () => {
    const input: CheckInput = {
      name: "Nyeri Agroforestry Stand",
      lat: -0.42,
      lon: 36.95,
      area_ha: 4.0,
      pathway: "agroforestry",
      practice: "shade_trees",
      stems_planted_per_ha: 140,
      tree_species: "Grevillea robusta",
      tenure: "owned_title",
      tenure_reference: "TITLE-NYERI-101",
      measurement_tier: 1,
    };

    const res = evaluateField(input);
    expect(res.eligibility).toBe("PASS");
    expect(res.methodology).toBe("VM0047");
    expect(res.bufferDeductionPct).toBe(15); // Forestry non-permanence buffer pool
    expect(res.netCreditsTonnesYear).toBeGreaterThan(0);
    expect(res.yieldPerHectare).toBeGreaterThan(0);
  });

  it("calculates Tier 3 measurement zero uncertainty bonus correctly", () => {
    const base: CheckInput = {
      name: "Flux Tower Field",
      lat: 10.787,
      lon: 79.138,
      area_ha: 10.0,
      pathway: "rice",
      practice: "awd",
      tenure: "owned_title",
      tenure_reference: "DOC-1",
      water_control: "full",
      rice_ecosystem: "irrigated_lowland",
      measurement_tier: 1,
    };

    const tier1 = evaluateField({ ...base, measurement_tier: 1 });
    const tier3 = evaluateField({ ...base, measurement_tier: 3 });

    expect(tier1.uncertaintyDeductionPct).toBe(35);
    expect(tier3.uncertaintyDeductionPct).toBe(0);
    // Tier 3 issues significantly more credits for the same land!
    expect(tier3.netCreditsTonnesYear).toBeGreaterThan(tier1.netCreditsTonnesYear);
  });

  it("provides realistic climatology and simulated Sentinel-1 radar passes", () => {
    const climate = estimateClimate(10.787, 79.138);
    expect(climate.monthlyRainMm.length).toBe(12);
    expect(climate.meanTempC).toBeGreaterThan(20);

    const radar = simulateSentinelRadarPasses("rice", 2, 105);
    expect(radar.samplePasses.length).toBeGreaterThan(10);
    expect(radar.samplePasses.some((p) => p.state === "drained")).toBe(true);
    expect(radar.samplePasses.some((p) => p.state === "flooded")).toBe(true);
  });
});

describe("saved-locations-store", () => {
  it("returns default seed fields when initialized", () => {
    const fields = getSavedFields();
    expect(fields.length).toBeGreaterThanOrEqual(3);
    expect(fields[0].name).toBeTruthy();
    expect(fields[0].result.netCreditsTonnesYear).toBeGreaterThan(0);
  });

  it("can export fields to GeoJSON and CSV", () => {
    const geojson = exportFieldsGeoJSON();
    const parsed = JSON.parse(geojson);
    expect(parsed.type).toBe("FeatureCollection");
    expect(parsed.features.length).toBeGreaterThanOrEqual(3);

    const csv = exportFieldsCSV();
    expect(csv).toContain("Field ID");
    expect(csv).toContain("Gross tCO2e/yr");
  });
});
