import { describe, expect, it } from "vitest";

import { measure } from "./geo";
import {
  parseSeasons,
  previewFarmFeatures,
  previewFarms,
  previewPractices,
  previewSoil,
  squareAround,
  templateCsv,
} from "./import";

describe("farm import", () => {
  it("accepts its own template unchanged", () => {
    const p = previewFarms(templateCsv("farms"));
    expect(p.failed).toBe(0);
    expect(p.ok).toBe(1);
    const farm = p.results[0].value!;
    expect(farm.status).toBe("enrolled");
    expect(farm.area_ha).toBeCloseTo(2.49, 1);
    expect(farm.seasons.map((s) => s.name)).toEqual(["Kuruvai", "Samba"]);
    expect(farm.farmer?.name).toBe("Murugan K");
  });

  it("maps the column names people actually use", () => {
    const csv = "Plot ID,Farmer,Latitude,Longitude,Hectares\nP-7,Wanjiru,-0.435,36.961,2.8\n";
    const p = previewFarms(csv);
    const farm = p.results[0].value!;
    expect(farm.name).toBe("P-7");
    expect(farm.farmer?.name).toBe("Wanjiru");
    expect(farm.area_ha).toBeCloseTo(2.8, 1);
  });

  it("imports a point-only legacy record as a draft and says why", () => {
    const p = previewFarms("farm_name,lat,lon,area_ha\nOld record,10.78,79.13,1.5\n");
    const r = p.results[0];
    expect(r.value?.status).toBe("draft");
    expect(r.warnings.join()).toMatch(/survey it/);
  });

  it("reports every problem in a bad row, with its spreadsheet row number", () => {
    const csv =
      "farm_name,boundary,tenure,enrolled_on,seasons\n" +
      "Good,\"POLYGON ((79.1378 10.7867, 79.1398 10.7868, 79.1396 10.7878, 79.1378 10.7867))\",owned_title,2025-06-01,\n" +
      "Bad,,freehold,01/06/2025,Kuruvai:13-01/09-25\n";
    const p = previewFarms(csv);
    expect(p.ok).toBe(1);
    const bad = p.results[1];
    expect(bad.row).toBe(3);
    const msg = bad.errors.join(" | ");
    expect(msg).toMatch(/needs a boundary/);
    expect(msg).toMatch(/tenure: "freehold"/);
    expect(msg).toMatch(/enrolled_on: use YYYY-MM-DD/);
    expect(msg).toMatch(/impossible month/);
  });

  it("refuses duplicate farm references within one file", () => {
    const row = "X-1,10.78,79.13,1\n";
    const p = previewFarms("farm_ref,lat,lon,area_ha\n" + row + row);
    expect(p.ok).toBe(1);
    expect(p.results[1].errors.join()).toMatch(/repeats row 2/);
  });

  it("warns, without failing, when paperwork is missing", () => {
    const p = previewFarms("farm_name,lat,lon,area_ha,tenure\nA,10.78,79.13,1,owned_title\n");
    expect(p.results[0].warnings.join()).toMatch(/reference document/);
    expect(p.results[0].warnings.join()).toMatch(/no farmer named/);
  });

  it("turns GeoJSON features into farm rows using their properties", () => {
    const p = previewFarmFeatures([
      {
        name: "From QGIS",
        properties: { Farmer: "Asha", plot_id: "Q-1", Tenure: "registered_lease" },
        geometry: squareAround(10.78, 79.13, 2),
      },
    ]);
    const farm = p.results[0].value!;
    expect(farm.name).toBe("From QGIS");
    expect(farm.external_ref).toBe("Q-1");
    expect(farm.farmer?.name).toBe("Asha");
    expect(farm.tenure).toBe("registered_lease");
  });
});

describe("helpers", () => {
  it("draws a square of the stated area", () => {
    expect(measure(squareAround(-0.435, 36.96, 2.8)).area_ha).toBeCloseTo(2.8, 2);
    expect(measure(squareAround(60, 10, 5)).area_ha).toBeCloseTo(5, 1);
  });

  it("parses a wrapping season", () => {
    const errors: string[] = [];
    expect(parseSeasons("Samba:08-20/01-20", errors)).toEqual([
      { name: "Samba", start_month: 8, start_day: 20, end_month: 1, end_day: 20 },
    ]);
    expect(errors).toEqual([]);
  });
});

describe("practice and soil import", () => {
  it("accepts the templates", () => {
    expect(previewPractices(templateCsv("practices")).failed).toBe(0);
    expect(previewSoil(templateCsv("soil")).failed).toBe(0);
  });

  it("catches inverted dates and depths", () => {
    const pr = previewPractices("farm_ref,year,practice,started_on,ended_on\nA,2025,awd,2025-09-01,2025-06-01\n");
    expect(pr.results[0].errors.join()).toMatch(/before started_on/);
    const soil = previewSoil("farm_ref,sampled_on,depth_top_cm,depth_bottom_cm,soc_pct\nA,2025-05-01,30,0,0.8\n");
    expect(soil.results[0].errors.join()).toMatch(/below depth_top_cm/);
  });

  it("warns when SOC looks like g/kg typed as %", () => {
    const soil = previewSoil("farm_ref,sampled_on,depth_top_cm,depth_bottom_cm,soc_pct,bulk_density\nA,2025-05-01,0,30,12,1.3\n");
    expect(soil.results[0].value).toBeDefined();
    expect(soil.results[0].warnings.join()).toMatch(/g\/kg/);
  });
});
