import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AggregationLine, YearBars } from "@/components/charts";
import { Button, Card, CardHeader, Field, Input, Notice, PageHeader, Select, Stat, Table, Td, Th } from "@/components/ui";
import {
  demoForecast,
  getOrgContext,
  getProject,
  listEstimates,
  listFarms,
  listVintages,
} from "@/lib/data";
import { EngineError, type ForecastResult, runForecast } from "@/lib/engine";
import { DEMO } from "@/lib/env";
import { buildProjections, enrolledUnits, type Projection } from "@/lib/forecast";
import { fmt } from "@/lib/format";

export const metadata: Metadata = { title: "Forward sales" };

type Params = {
  basis?: string;
  horizon?: string;
  confidence?: string;
  dropout?: string;
  lapse?: string;
  failure?: string;
  slip?: string;
  commit?: string;
  price?: string;
};

const pct = (s: string | undefined, fallback: number) => {
  const n = Number(s);
  return s !== undefined && s !== "" && Number.isFinite(n) ? Math.min(Math.max(n, 0), 95) / 100 : fallback;
};

export default async function ForecastPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Params>;
}) {
  const [{ id }, q] = await Promise.all([params, searchParams]);
  const ctx = await getOrgContext();
  const project = await getProject(ctx.org.id, id);
  if (!project) notFound();
  const [farms, estimates, vintages] = await Promise.all([
    listFarms(ctx.org.id, { projectId: id }),
    listEstimates(ctx.org.id),
    listVintages(ctx.org.id, id),
  ]);

  const currentYear = new Date().getUTCFullYear();
  const horizon = Math.min(Math.max(Number(q.horizon) || 4, 1), 10);
  const basis = q.basis === "potential" ? "potential" : "creditable";
  const confidence = [0.8, 0.9, 0.95].includes(Number(q.confidence)) ? Number(q.confidence) : 0.9;
  const risk = {
    dropout_per_year: pct(q.dropout, 0.08),
    practice_lapse_per_year: pct(q.lapse, 0.12),
    planting_failure_per_year: pct(q.failure, 0.05),
    verification_slip_per_year: pct(q.slip, 0.18),
  };
  const commit = Number(q.commit) > 0 ? Number(q.commit) : null;
  const price = Number(q.price) > 0 ? Number(q.price) : 30;
  const customised = Object.values(q).some((v) => v !== undefined && v !== "");

  const farmIds = new Set(farms.map((f) => f.id));
  const projections: Projection[] = buildProjections(
    estimates.filter((e) => farmIds.has(e.farm_id)),
    farms,
    vintages,
    { basis, through: currentYear + horizon, currentYear },
  );
  const units = enrolledUnits(farms);
  const track = project.pathway === "soil" ? "cropland" : project.pathway === "other" ? "agroforestry" : project.pathway;

  let result: ForecastResult | null = null;
  let problem: string | null = null;
  let demoNote = false;
  if (DEMO) {
    result = (demoForecast(id)?.result as ForecastResult | undefined) ?? null;
    demoNote = customised;
  } else if (!projections.length) {
    problem = "Nothing to forecast yet: run estimates on this project's farms first.";
  } else {
    try {
      result = await runForecast({
        project_id: project.id,
        track,
        enrolled_units: units,
        confidence,
        risk,
        projections: projections.map((p) => ({
          year: p.year,
          net_t: p.net_t,
          relative_uncertainty: p.relative_uncertainty,
          settled: p.settled,
        })),
        ...(commit ? { offtake: { committed_t: commit, replacement_price: price } } : {}),
      });
    } catch (e) {
      problem = e instanceof EngineError ? e.message : `Forecast failed: ${(e as Error).message}`;
    }
  }
  const f = result?.forecast;
  const carried = new Set(projections.filter((p) => p.carried).map((p) => p.year));

  return (
    <>
      <PageHeader
        crumbs={[
          { href: "/app/projects", label: "Projects" },
          { href: `/app/projects/${project.id}`, label: project.name },
        ]}
        title="How much can be sold forward"
        description="Thousands of simulated futures in which farmers leave, seasons lapse, plantings fail and verification slips. The safe volume is what the project delivers in the chosen share of them; selling the median means missing half the time and buying the shortfall at spot."
      />

      <div className="grid gap-6 lg:grid-cols-4">
        <Card className="h-fit lg:order-2">
          <CardHeader title="Assumptions" description="Placeholder rates until you have your own history." />
          <form className="flex flex-col gap-3 p-5">
            <Field label="Count">
              <Select name="basis" defaultValue={basis}>
                <option value="creditable">What is creditable now</option>
                <option value="potential">Potential, if paperwork is fixed</option>
              </Select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Years ahead">
                <Input name="horizon" type="number" min={1} max={10} defaultValue={horizon} />
              </Field>
              <Field label="Confidence">
                <Select name="confidence" defaultValue={String(confidence)}>
                  <option value="0.8">80%</option>
                  <option value="0.9">90%</option>
                  <option value="0.95">95%</option>
                </Select>
              </Field>
              <Field label="Farmers leaving / yr %">
                <Input name="dropout" type="number" step="1" min={0} max={95} defaultValue={risk.dropout_per_year * 100} />
              </Field>
              <Field label="Seasons lapsed / yr %">
                <Input name="lapse" type="number" step="1" min={0} max={95} defaultValue={risk.practice_lapse_per_year * 100} />
              </Field>
              <Field label="Plantings failed / yr %">
                <Input name="failure" type="number" step="1" min={0} max={95} defaultValue={risk.planting_failure_per_year * 100} />
              </Field>
              <Field label="Verification slips / yr %">
                <Input name="slip" type="number" step="1" min={0} max={95} defaultValue={risk.verification_slip_per_year * 100} />
              </Field>
            </div>
            <h3 className="mt-2 text-sm font-semibold">Test a sale</h3>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Tonnes promised">
                <Input name="commit" type="number" step="0.1" min={0} defaultValue={commit ?? ""} />
              </Field>
              <Field label="Spot price to cover ($)">
                <Input name="price" type="number" step="1" min={0} defaultValue={price} />
              </Field>
            </div>
            <Button type="submit">Run forecast</Button>
          </form>
        </Card>

        <div className="flex flex-col gap-6 lg:order-1 lg:col-span-3">
          {problem && <Notice tone="accent">{problem}</Notice>}
          {demoNote && (
            <Notice tone="info">
              The demo shows the forecast at default assumptions. Connect the engine to rerun it with your own.
            </Notice>
          )}
          {f && result && (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <Stat label="Projected" value={fmt.t(f.projected_total_t)} hint="the point estimate" />
                <Stat label="Median" value={fmt.t(f.p50_total_t)} />
                <Stat
                  label={`Safe at ${fmt.pct(f.confidence)}`}
                  value={fmt.t(f.safe_total_t)}
                  tone="brand"
                  hint="what may be promised"
                />
                <Stat label="Haircut" value={fmt.pct(f.portfolio_haircut)} hint="of the projection is not safe to sell" />
              </div>

              {result.offtake && (
                <Notice
                  tone={result.offtake.verdict.startsWith("signable") ? "brand" : result.offtake.verdict.startsWith("do not") ? "danger" : "accent"}
                  title={`Promising ${fmt.t(result.offtake.committed_t)}: ${result.offtake.verdict}`}
                >
                  Delivers in {fmt.pct(result.offtake.delivery_probability)} of futures. Expected shortfall{" "}
                  {fmt.t(result.offtake.expected_shortfall_t, 2)}, costing about{" "}
                  {fmt.money(result.offtake.expected_cover_cost)} to cover at {fmt.money(result.offtake.replacement_price)}/t;
                  worst case {fmt.t(result.offtake.worst_case_shortfall_t)}.
                </Notice>
              )}

              <Card>
                <CardHeader title="By year" description="Projected tonnes, and the part of each year that is safe to sell." />
                <div className="p-5">
                  <YearBars
                    data={f.years.map((y) => ({ year: y.year, projected: y.projected_t, safe: y.safe_t }))}
                    bars={[
                      { key: "projected", label: "Projected", color: "var(--info)" },
                      { key: "safe", label: "Safe to sell", color: "var(--brand)" },
                    ]}
                  />
                </div>
                <Table>
                  <thead>
                    <tr>
                      <Th>Year</Th>
                      <Th className="text-right">Projected</Th>
                      <Th className="text-right">P10</Th>
                      <Th className="text-right">Median</Th>
                      <Th className="text-right">P90</Th>
                      <Th className="text-right">Safe</Th>
                      <Th>Basis</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {f.years.map((y) => {
                      const p = projections.find((x) => x.year === y.year);
                      return (
                        <tr key={y.year}>
                          <Td>{y.year}</Td>
                          <Td className="tabular text-right">{fmt.num(y.projected_t, 1)}</Td>
                          <Td className="tabular text-right text-muted">{fmt.num(y.p10, 1)}</Td>
                          <Td className="tabular text-right">{fmt.num(y.p50, 1)}</Td>
                          <Td className="tabular text-right text-muted">{fmt.num(y.p90, 1)}</Td>
                          <Td className="tabular text-right font-medium text-brand">{fmt.num(y.safe_t, 1)}</Td>
                          <Td className="text-xs text-muted">
                            {p?.settled ? "verified" : carried.has(y.year) ? "carried forward" : "estimated"}
                          </Td>
                        </tr>
                      );
                    })}
                  </tbody>
                </Table>
                <p className="px-5 py-3 text-xs text-muted">
                  Each year&apos;s safe figure is that year on its own: a slipped verification moves a year&apos;s
                  credits into the next one, so any single year can come in at nothing. The total is safer than the sum
                  of years because bad years rarely all coincide, so promise against the total, not year by year. Years
                  no farm has been estimated for repeat the last complete year; flat is deliberately conservative, as
                  trees keep growing.
                </p>
              </Card>

              <div className="grid gap-6 xl:grid-cols-2">
                <Card>
                  <CardHeader
                    title="What each risk costs"
                    description="Safe volume recovered if that one risk disappeared. Fix the biggest first."
                  />
                  <ul className="space-y-3 p-5">
                    {Object.entries(f.sensitivity)
                      .map(([name, without]) => [name, without - f.safe_total_t] as const)
                      .sort((a, b) => b[1] - a[1])
                      .map(([name, cost]) => (
                        <li key={name}>
                          <div className="flex justify-between text-sm">
                            <span className="capitalize">{name}</span>
                            <span className="tabular">{fmt.t(cost)}</span>
                          </div>
                          <div className="mt-1 h-1.5 rounded-full bg-surface-2">
                            <div
                              className="h-1.5 rounded-full bg-accent"
                              style={{
                                width: `${Math.max(2, (cost / Math.max(...Object.values(f.sensitivity).map((w) => w - f.safe_total_t), 0.001)) * 100)}%`,
                              }}
                            />
                          </div>
                        </li>
                      ))}
                  </ul>
                </Card>
                <Card>
                  <CardHeader
                    title="Aggregation"
                    description={`This project has ${result.risk.enrolled_units} independent farmers. More farmers diversify away attrition and failure.`}
                  />
                  <div className="p-5">
                    <AggregationLine data={result.aggregation} current={result.risk.enrolled_units} />
                  </div>
                </Card>
              </div>
              <p className="text-xs text-muted">
                {f.trials.toLocaleString()} seeded simulations, reproducible. Risk rates: {result.risk.source}.
              </p>
            </>
          )}
        </div>
      </div>
    </>
  );
}
