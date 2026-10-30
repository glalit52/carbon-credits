import { createHash } from "node:crypto";

import { describe, expect, it } from "vitest";

import type { Estimate, Farm, Farmer, Project, Vintage } from "./database.types";
import { buildPack, type PackInput } from "./evidence-pack";

const dec = new TextDecoder();

function input(over: Partial<PackInput> = {}): PackInput {
  const farm = { id: "f1", name: "Plot 1", external_ref: "TNJ-1", farmer_id: "u1", area_ha: 1.2,
    boundary: { type: "Polygon", coordinates: [[[79, 10], [79.01, 10], [79.01, 10.01], [79, 10]]] } } as unknown as Farm;
  const run = "2026-10-01T00:00:00Z";
  const est = (id: string, year: number, monitoring?: object) =>
    ({ id, farm_id: "f1", year, created_at: run, net_t: 1, gross_t: 2, data_quality: "simulated monitoring",
       input: { farm: {} }, result: { vintages: [{ year }], blockers: [], ...(monitoring ? { monitoring } : {}) } }) as unknown as Estimate;
  return {
    generatedAt: "2026-10-30T00:00:00Z",
    generatedBy: "Tester",
    organisation: "Acme",
    project: { name: "Cauvery", methodology: "VM0051", registry: "Verra" } as Project,
    vintage: { id: "v1", year: 2025, status: "issued", gross_t: 2, net_t: 1, issuable: 1, serial_start: 1,
      serial_end: 1, registry_ref: null, updated_at: run,
      derivation: { method: "sum", farms: [{ farm_id: "f1", estimate_id: "e2025", net_t: 1, gross_t: 2 }] } } as unknown as Vintage,
    events: [],
    farms: [farm],
    farmers: [{ id: "u1", name: "Murugan", external_ref: "F1" } as Farmer],
    // The vintage names the 2025 row; the run's monitoring sits on the 2026 row.
    estimateRows: [
      est("e2025", 2025),
      est("e2026", 2026, { simulated: true, years: [2025, 2026], optical: [], regimes: [],
        radar: [{ day: "2025-07-01", season: "Kuruvai", vv_db: -9, vh_db: -16, state: "flooded", p_flooded: 0.9,
                  confidence: 0.8, inferred: false, note: "" },
                { day: "2023-07-01", season: "Kuruvai", vv_db: -9, vh_db: -16, state: "drained", p_flooded: 0.1,
                  confidence: 0.8, inferred: false, note: "" }] }),
    ],
    practices: [], soil: [], loggers: [], payments: [], retirements: [], claims: null, audit: [],
    names: new Map(), attachments: new Map(), missingAttachments: [],
    ...over,
  };
}

describe("buildPack", () => {
  it("uses the exact estimate the vintage names, and its run's monitoring", () => {
    const files = buildPack(input());
    const calc = JSON.parse(dec.decode(files.get("calculations/TNJ-1.json")));
    expect(calc.estimate_id).toBe("e2025");
    const radar = dec.decode(files.get("observations/radar_passes.csv")).trim().split("\r\n");
    expect(radar).toHaveLength(2); // header + the 2025 pass; 2023 is outside the vintage
    expect(radar[1]).toContain("2025-07-01");
  });

  it("hashes every file in the manifest", () => {
    const files = buildPack(input());
    const manifest = JSON.parse(dec.decode(files.get("manifest.json")));
    expect(manifest.files.length).toBe(files.size - 1);
    for (const f of manifest.files) {
      expect(createHash("sha256").update(files.get(f.path)!).digest("hex")).toBe(f.sha256);
    }
  });

  it("says when the vintage names an estimate it can no longer read", () => {
    const files = buildPack(input({ estimateRows: [] }));
    expect(JSON.parse(dec.decode(files.get("manifest.json"))).missing_estimates).toEqual(["e2025"]);
    expect(dec.decode(files.get("README.md"))).toContain("no longer readable");
  });

  it("flags simulated monitoring up front", () => {
    expect(dec.decode(buildPack(input()).get("README.md"))).toMatch(/\*\*simulated\*\*/);
  });
});
