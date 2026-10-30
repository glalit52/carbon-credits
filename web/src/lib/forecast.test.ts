import { describe, expect, it } from "vitest";

import type { Estimate, Farm, Vintage } from "./database.types";
import { buildProjections, enrolledUnits } from "./forecast";

function farm(id: string, status: Farm["status"] = "enrolled", farmer: string | null = id): Farm {
  return { id, status, farmer_id: farmer } as Farm;
}

function est(farm_id: string, year: number, net: number, potential: number, unc = 0.1): Estimate {
  return {
    farm_id,
    year,
    net_t: net,
    result: { vintages: [{ year, relative_uncertainty: unc, potential: { net_t: potential, relative_uncertainty: unc } }] },
  } as unknown as Estimate;
}

const opts = { basis: "creditable" as const, through: 2028, currentYear: 2026 };

describe("buildProjections", () => {
  it("sums enrolled farms per year and ignores withdrawn ones", () => {
    const p = buildProjections(
      [est("a", 2025, 2, 2), est("b", 2025, 3, 3), est("w", 2025, 100, 100)],
      [farm("a"), farm("b"), farm("w", "withdrawn")],
      [],
      { ...opts, through: 2025 },
    );
    expect(p).toEqual([{ year: 2025, net_t: 5, relative_uncertainty: 0.1, settled: false, carried: false }]);
  });

  it("counts potential when asked, creditable otherwise", () => {
    const e = [est("a", 2025, 0, 4)];
    expect(buildProjections(e, [farm("a")], [], { ...opts, through: 2025 })[0].net_t).toBe(0);
    expect(buildProjections(e, [farm("a")], [], { ...opts, through: 2025, basis: "potential" })[0].net_t).toBe(4);
  });

  it("marks approved and issued years settled", () => {
    const p = buildProjections([est("a", 2025, 1, 1)], [farm("a")], [{ year: 2025, status: "issued" } as Vintage], {
      ...opts,
      through: 2025,
    });
    expect(p[0].settled).toBe(true);
  });

  it("carries the last complete year forward, not the year in progress", () => {
    const p = buildProjections([est("a", 2025, 5, 5), est("a", 2026, 2, 2)], [farm("a")], [], opts);
    expect(p.map((x) => [x.year, x.net_t, x.carried])).toEqual([
      [2025, 5, false],
      [2026, 2, false],
      [2027, 5, true],
      [2028, 5, true],
    ]);
  });

  it("weights uncertainty by tonnes", () => {
    const p = buildProjections([est("a", 2025, 9, 9, 0.1), est("b", 2025, 1, 1, 0.5)], [farm("a"), farm("b")], [], {
      ...opts,
      through: 2025,
    });
    expect(p[0].relative_uncertainty).toBeCloseTo(0.14);
  });
});

describe("enrolledUnits", () => {
  it("counts distinct farmers on enrolled farms", () => {
    expect(enrolledUnits([farm("a", "enrolled", "f1"), farm("b", "enrolled", "f1"), farm("c", "draft", "f2")])).toBe(1);
    expect(enrolledUnits([])).toBe(1);
  });
});
