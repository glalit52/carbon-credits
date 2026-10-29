import { ArrowRight, Plus, Upload } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { YearBars } from "@/components/charts";
import { FarmMap } from "@/components/map/farm-map";
import { Badge, ButtonLink, Card, CardHeader, EmptyState, PageHeader, Stat } from "@/components/ui";
import {
  getOrgContext,
  listAudit,
  listEstimates,
  listFarmers,
  listFarms,
  listPayments,
  listProjects,
  listVintages,
  memberNames,
} from "@/lib/data";
import type { EngineResult } from "@/lib/engine";
import { fmt, VINTAGE_LABEL, VINTAGE_TONE } from "@/lib/format";
import { readiness } from "@/lib/readiness";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Overview" };

const PROJECT_COLORS = ["var(--brand)", "var(--info)", "var(--accent)", "#8b5cf6", "#0ea5e9"];

function describe(entity: string, action: string, detail: unknown): string {
  const d = (detail ?? {}) as Record<string, unknown>;
  const noun = { farms: "farm", farmers: "farmer", vintages: "vintage", payments: "payment", projects: "project" }[entity] ?? entity;
  if (action === "insert") return `added ${noun}${d.name ? ` “${d.name}”` : ""}`;
  if (action === "delete") return `deleted a ${noun}`;
  if (d.status) return `moved a ${noun} to ${String(d.status).replace("_", " ")}`;
  return `updated a ${noun}`;
}

export default async function Overview() {
  const ctx = await getOrgContext();
  const [projects, farms, farmers, estimates, vintages, payments, audit, names] = await Promise.all([
    listProjects(ctx.org.id),
    listFarms(ctx.org.id),
    listFarmers(ctx.org.id),
    listEstimates(ctx.org.id),
    listVintages(ctx.org.id),
    listPayments(ctx.org.id),
    listAudit(ctx.org.id, 12),
    memberNames(ctx.org.id),
  ]);

  if (farms.length === 0 && projects.length === 0) {
    return (
      <>
        <PageHeader title={`Welcome to ${ctx.org.name}`} />
        <Card>
          <EmptyState
            title="Let's get your first farms in"
            body="Create a project for each pathway and region, then add farms one by one or import the records you already have."
            action={
              can.manage(ctx.role) && (
                <div className="flex flex-wrap justify-center gap-2">
                  <ButtonLink href="/app/projects/new">Create a project</ButtonLink>
                  <ButtonLink href="/app/import" variant="secondary">
                    Import existing data
                  </ButtonLink>
                </div>
              )
            }
          />
        </Card>
      </>
    );
  }

  const farmProject = new Map(farms.map((f) => [f.id, f.project_id]));
  const projectById = new Map(projects.map((p) => [p.id, p]));
  const farmerById = new Map(farmers.map((f) => [f.id, f]));
  const potentialOf = (e: (typeof estimates)[number]) =>
    (e.result as unknown as EngineResult).vintages?.[0]?.potential?.net_t ?? 0;

  const years = [...new Set(estimates.map((e) => e.year))].sort();
  const byYear = years.map((year) => {
    const row: Record<string, number | string> = { year };
    for (const p of projects) {
      row[p.id] = estimates
        .filter((e) => e.year === year && farmProject.get(e.farm_id) === p.id)
        .reduce((s, e) => s + potentialOf(e), 0);
    }
    return row;
  });

  const potential = estimates.reduce((s, e) => s + potentialOf(e), 0);
  const creditable = estimates.reduce((s, e) => s + Number(e.net_t), 0);
  const issued = vintages.filter((v) => v.status === "issued").reduce((s, v) => s + v.issuable, 0);
  const paid = payments.filter((p) => p.status === "paid").reduce((s, p) => s + Number(p.amount), 0);
  const area = farms.reduce((s, f) => s + Number(f.area_ha), 0);

  // What stops farms being credited, most common first.
  const blockers = new Map<string, number>();
  let readyFarms = 0;
  for (const f of farms) {
    const checks = readiness(f, farmerById.get(f.farmer_id ?? "") ?? null, projectById.get(f.project_id ?? "") ?? null);
    const failing = checks.filter((c) => !c.ok);
    if (!failing.length) readyFarms++;
    for (const c of failing) blockers.set(c.label, (blockers.get(c.label) ?? 0) + 1);
  }
  const topBlockers = [...blockers].sort((a, b) => b[1] - a[1]).slice(0, 5);

  return (
    <>
      <PageHeader
        title="Overview"
        description={`${ctx.org.name} · ${farms.length} farms across ${projects.length} projects`}
        actions={
          can.enrol(ctx.role) && (
            <>
              <ButtonLink href="/app/import" variant="secondary">
                <Upload className="h-4 w-4" /> Import
              </ButtonLink>
              <ButtonLink href="/app/farms/new">
                <Plus className="h-4 w-4" /> Add farm
              </ButtonLink>
            </>
          )
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Stat label="Farms" value={fmt.int(farms.length)} hint={`${readyFarms} ready to credit`} />
        <Stat label="Farmers" value={fmt.int(farmers.length)} />
        <Stat label="Area" value={fmt.ha(area)} />
        <Stat label="Potential" value={fmt.t(potential)} hint="all estimated years" tone="brand" />
        <Stat label="Issued" value={fmt.int(issued)} hint="whole credits" />
        <Stat label="Paid to farmers" value={fmt.money(paid, payments[0]?.currency ?? "USD")} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Estimated credits by year"
            description={`Potential net tCO₂e per project. ${fmt.t(potential - creditable)} of it is waiting on farm paperwork.`}
          />
          <div className="p-5">
            {byYear.length ? (
              <YearBars
                data={byYear}
                bars={projects.map((p, i) => ({ key: p.id, label: p.name, color: PROJECT_COLORS[i % PROJECT_COLORS.length], stack: "p" }))}
                height={280}
              />
            ) : (
              <EmptyState title="No estimates yet" body="Open a farm and run its estimate." />
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="What blocks crediting" description={`${farms.length - readyFarms} of ${farms.length} farms have open items`} />
          {topBlockers.length ? (
            <ul className="space-y-3 p-5">
              {topBlockers.map(([label, n]) => (
                <li key={label}>
                  <div className="flex justify-between text-sm">
                    <span>{label}</span>
                    <span className="tabular text-muted">{n}</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-surface-2">
                    <div className="h-1.5 rounded-full bg-accent" style={{ width: `${(n / farms.length) * 100}%` }} />
                  </div>
                </li>
              ))}
              <li>
                <Link href="/app/farms" className="flex items-center gap-1 text-sm font-medium text-brand">
                  Work through farms <ArrowRight className="h-4 w-4" />
                </Link>
              </li>
            </ul>
          ) : (
            <EmptyState title="Every farm is ready" />
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <FarmMap
            farms={farms.map((f) => ({ id: f.id, name: f.name, boundary: f.boundary, status: f.status, area_ha: Number(f.area_ha) }))}
            className="h-96"
          />
        </div>
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader title="Vintages" action={<Link href="/app/credits" className="text-xs font-medium text-brand">All</Link>} />
            <ul className="divide-y divide-border">
              {vintages.slice(0, 5).map((v) => (
                <li key={v.id}>
                  <Link href={`/app/credits/${v.id}`} className="flex items-center justify-between gap-2 px-5 py-3 text-sm hover:bg-surface-2">
                    <span className="truncate">
                      {projectById.get(v.project_id)?.name} · {v.year}
                    </span>
                    <Badge tone={VINTAGE_TONE[v.status]}>{VINTAGE_LABEL[v.status]}</Badge>
                  </Link>
                </li>
              ))}
              {!vintages.length && <li className="px-5 py-4 text-sm text-muted">None yet.</li>}
            </ul>
          </Card>
          <Card>
            <CardHeader title="Recent activity" action={<Link href="/app/activity" className="text-xs font-medium text-brand">All</Link>} />
            <ul className="divide-y divide-border text-sm">
              {audit.slice(0, 6).map((a) => (
                <li key={a.id} className="px-5 py-2.5">
                  <span className="font-medium">{names.get(a.actor ?? "") ?? "System"}</span>{" "}
                  <span className="text-muted">{describe(a.entity, a.action, a.detail)}</span>
                  <div className="text-xs text-muted">{fmt.datetime(a.at)}</div>
                </li>
              ))}
              {!audit.length && <li className="px-5 py-4 text-muted">Nothing yet.</li>}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
