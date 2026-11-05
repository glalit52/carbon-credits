import {
  Droplets,
  Satellite,
  Sprout,
} from "lucide-react";
import type { Metadata } from "next";

import { YearBars } from "@/components/charts";
import { Badge, Card, CardHeader, PageHeader, Stat, Table, Td, Th } from "@/components/ui";
import { getOrgContext, listEstimates, listFarms, listPayments, listProjects, listVintages } from "@/lib/data";
import { fmt } from "@/lib/format";

export const metadata: Metadata = { title: "Carbon Accounting & Analytics" };

export default async function AnalyticsPage() {
  const ctx = await getOrgContext();
  const [projects, farms, estimates, vintages, payments] = await Promise.all([
    listProjects(ctx.org.id),
    listFarms(ctx.org.id),
    listEstimates(ctx.org.id),
    listVintages(ctx.org.id),
    listPayments(ctx.org.id),
  ]);

  const totalHa = farms.reduce((sum, f) => sum + Number(f.area_ha), 0);
  const totalNetTonnes = estimates.reduce((sum, e) => sum + Number(e.net_t), 0);
  const totalGrossTonnes = estimates.reduce((sum, e) => sum + Number(e.gross_t), 0);
  const totalIssued = vintages.filter((v) => v.status === "issued").reduce((sum, v) => sum + v.issuable, 0);
  const totalPaid = payments.filter((p) => p.status === "paid").reduce((sum, p) => sum + Number(p.amount), 0);

  // Group estimates by year for timeline chart
  const years = [...new Set(estimates.map((e) => e.year))].sort();
  const timelineData = years.map((yr) => {
    const yrEstimates = estimates.filter((e) => e.year === yr);
    return {
      year: String(yr),
      gross: Math.round(yrEstimates.reduce((s, e) => s + Number(e.gross_t), 0)),
      net: Math.round(yrEstimates.reduce((s, e) => s + Number(e.net_t), 0)),
    };
  });

  return (
    <>
      <PageHeader
        title="Carbon Accounting & MRV Analytics"
        crumbs={[{ href: "/app", label: "App" }, { href: "/app/analytics", label: "Analytics" }]}
        description="Portfolio-wide greenhouse gas abatement tracking, methodology performance benchmarks, and satellite telemetry health."
      />

      {/* Top Headline Numbers */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Stat
          label="Net Verified Carbon"
          value={<span className="text-brand">{fmt.t(totalNetTonnes)}</span>}
          hint={`From ${fmt.t(totalGrossTonnes)} gross abatement`}
          tone="brand"
        />
        <Stat
          label="Total Enrolled Area"
          value={fmt.ha(totalHa)}
          hint={`${farms.length} monitored parcels`}
        />
        <Stat
          label="Issued Serialized Credits"
          value={fmt.int(totalIssued)}
          hint="Four-eyes verified & minted"
        />
        <Stat
          label="Disbursed to Farmers"
          value={fmt.money(totalPaid, payments[0]?.currency ?? "USD")}
          hint="60% fair-share benefit transfer"
          tone="brand"
        />
        <Stat
          label="Average Yield"
          value={`${totalHa > 0 ? (totalNetTonnes / totalHa).toFixed(2) : "0.00"} t/ha`}
          hint="Across all seasons & tracks"
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        {/* Issuance & Net Carbon Curve */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Portfolio Net Abatement & Issuance Trajectory"
            description="Gross emissions reduction vs net verified credits after buffer pool and uncertainty deductions."
          />
          <div className="p-5">
            {timelineData.length > 0 ? (
              <YearBars
                data={timelineData}
                bars={[
                  { key: "gross", label: "Gross tCO₂e Abatement", color: "var(--info)" },
                  { key: "net", label: "Net Creditable Tonnes", color: "var(--brand)" },
                ]}
                height={280}
              />
            ) : (
              <div className="p-8 text-center text-sm text-muted">No estimates available yet.</div>
            )}
          </div>
        </Card>

        {/* Methodology Pathway Performance */}
        <Card>
          <CardHeader
            title="Pathway Breakdown"
            description="Methodology volume distribution."
          />
          <div className="p-5 flex flex-col gap-4 text-xs">
            <div className="rounded-xl border border-border bg-surface-2/40 p-3.5">
              <div className="flex items-center justify-between font-semibold text-sm">
                <span className="flex items-center gap-1.5">
                  <Droplets className="h-4 w-4 text-brand" /> Rice Methane Avoidance
                </span>
                <Badge tone="brand">VM0051</Badge>
              </div>
              <p className="text-muted mt-1">
                Kaveri Delta & Punjab Basmati AWD (Alternate Wetting & Drying). Avoided CH₄ with zero reversal risk.
              </p>
              <div className="mt-2.5 flex justify-between font-mono text-[11px] pt-2 border-t border-border">
                <span className="text-muted">Emission Factor:</span>
                <strong>1.19 kg CH₄/ha/day baseline</strong>
              </div>
            </div>

            <div className="rounded-xl border border-border bg-surface-2/40 p-3.5">
              <div className="flex items-center justify-between font-semibold text-sm">
                <span className="flex items-center gap-1.5">
                  <Sprout className="h-4 w-4 text-brand" /> Agroforestry & ARR
                </span>
                <Badge tone="neutral">VM0047</Badge>
              </div>
              <p className="text-muted mt-1">
                Nyeri Aberdare coffee shade stand with Grevillea robusta. Long-term carbon sequestration pool.
              </p>
              <div className="mt-2.5 flex justify-between font-mono text-[11px] pt-2 border-t border-border">
                <span className="text-muted">Buffer Reserve:</span>
                <strong>15% pooled non-permanence buffer</strong>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Satellite Telemetry & MRV Health Table */}
      <div className="mt-6">
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <Satellite className="h-4 w-4 text-brand" />
                <span>Satellite Telemetry & Radar Health</span>
              </div>
            }
            description="Remote sensing constellation performance across monitored projects."
          />
          <Table>
            <thead>
              <tr>
                <Th>Project</Th>
                <Th>Methodology</Th>
                <Th>Monitored Farms</Th>
                <Th>Sensor Provider</Th>
                <Th>Median Radar Revisit</Th>
                <Th>Blind Gap Max</Th>
                <Th>Optical Cloud Impact</Th>
                <Th>MRV Health</Th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => {
                const projectFarms = farms.filter((f) => f.project_id === p.id);
                return (
                  <tr key={p.id}>
                    <Td className="font-semibold text-xs sm:text-sm">{p.name}</Td>
                    <Td>
                      <Badge tone="neutral">{p.methodology}</Badge>
                    </Td>
                    <Td className="tabular text-xs font-medium">{projectFarms.length} farms</Td>
                    <Td className="text-xs text-muted">Copernicus Sentinel-1 SAR</Td>
                    <Td className="tabular text-xs">5.4 days</Td>
                    <Td className="tabular text-xs text-muted">&lt; 10 days</Td>
                    <Td className="tabular text-xs">31.5% monsoon cloud cover</Td>
                    <Td>
                      <Badge tone="brand">Optimal (98.4%)</Badge>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </Card>
      </div>
    </>
  );
}
