import type { Estimate, Farm, Vintage } from "@/lib/database.types";
import type { EngineResult } from "@/lib/engine";

// Turn a project's farm estimates into the per-year projections the engine's
// forecast takes (src/carbonstack/forecast_api.py). Pure, so the page and the
// tests build exactly the same input.

export type Projection = { year: number; net_t: number; relative_uncertainty: number; settled: boolean; carried: boolean };

export type ProjectionOptions = {
  /** Count only what is creditable now, or assume blocked paperwork gets fixed. */
  basis: "creditable" | "potential";
  /** Last year to forecast, inclusive. */
  through: number;
  /** The current year: a year is complete only once it is over. */
  currentYear: number;
};

function vintageOf(e: Estimate) {
  return (e.result as unknown as EngineResult).vintages?.[0];
}

export function buildProjections(
  estimates: Estimate[],
  farms: Farm[],
  vintages: Vintage[],
  opts: ProjectionOptions,
): Projection[] {
  const enrolled = new Set(farms.filter((f) => f.status === "enrolled").map((f) => f.id));
  const byYear = new Map<number, { net: number; weightedUnc: number }>();
  for (const e of estimates) {
    if (!enrolled.has(e.farm_id)) continue;
    const v = vintageOf(e);
    const net = opts.basis === "potential" ? (v?.potential?.net_t ?? Number(e.net_t)) : Number(e.net_t);
    const unc = (opts.basis === "potential" ? v?.potential?.relative_uncertainty : v?.relative_uncertainty) ?? 0;
    const row = byYear.get(e.year) ?? { net: 0, weightedUnc: 0 };
    row.net += net;
    row.weightedUnc += net * unc;
    byYear.set(e.year, row);
  }
  const settledYears = new Set(
    vintages.filter((v) => v.status === "approved" || v.status === "issued").map((v) => v.year),
  );
  const out: Projection[] = [...byYear]
    .sort((a, b) => a[0] - b[0])
    .filter(([year]) => year <= opts.through)
    .map(([year, r]) => ({
      year,
      net_t: Math.round(r.net * 1e4) / 1e4,
      relative_uncertainty: r.net > 0 ? Math.round((r.weightedUnc / r.net) * 1e4) / 1e4 : 0,
      settled: settledYears.has(year),
      carried: false,
    }));

  // Years nobody has estimated yet repeat the last complete year. Flat is the
  // conservative choice: trees keep growing and rice holds roughly level, so
  // this understates rather than overstates what can be promised.
  const complete = out.filter((p) => p.year < opts.currentYear);
  const template = complete.at(-1) ?? out.at(-1);
  if (template) {
    const last = out.at(-1)!.year;
    for (let year = last + 1; year <= opts.through; year++) {
      out.push({ ...template, year, settled: false, carried: true });
    }
  }
  return out;
}

/** Independently-failing units: the farmers behind the enrolled farms. */
export function enrolledUnits(farms: Farm[]): number {
  const enrolled = farms.filter((f) => f.status === "enrolled");
  const farmers = new Set(enrolled.map((f) => f.farmer_id ?? f.id));
  return Math.max(1, farmers.size);
}
