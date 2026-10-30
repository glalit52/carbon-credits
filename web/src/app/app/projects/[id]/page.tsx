import { Download, Plus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/action-form";
import { YearBars } from "@/components/charts";
import { FarmMap } from "@/components/map/farm-map";
import { Badge, ButtonLink, Card, DownloadLink, CardHeader, EmptyState, PageHeader, Stat, Table, Td, Th } from "@/components/ui";
import { estimateProject } from "@/lib/actions/farms";
import { getOrgContext, getProject, listEstimates, listFarmers, listFarms, listVintages } from "@/lib/data";
import type { EngineResult } from "@/lib/engine";
import { fmt, PATHWAY_LABEL, VINTAGE_LABEL, VINTAGE_TONE } from "@/lib/format";
import { readiness, readyCount } from "@/lib/readiness";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Project" };

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ctx = await getOrgContext();
  const project = await getProject(ctx.org.id, id);
  if (!project) notFound();
  const [farms, farmers, estimates, vintages] = await Promise.all([
    listFarms(ctx.org.id, { projectId: id }),
    listFarmers(ctx.org.id),
    listEstimates(ctx.org.id),
    listVintages(ctx.org.id, id),
  ]);
  const farmIds = new Set(farms.map((f) => f.id));
  const farmerById = new Map(farmers.map((f) => [f.id, f]));
  const own = estimates.filter((e) => farmIds.has(e.farm_id));
  const years = [...new Set(own.map((e) => e.year))].sort();
  const chart = years.map((year) => {
    const ys = own.filter((e) => e.year === year);
    const creditable = ys.reduce((s, e) => s + Number(e.net_t), 0);
    const potential = ys.reduce((s, e) => s + ((e.result as unknown as EngineResult).vintages[0]?.potential?.net_t ?? 0), 0);
    return { year, creditable, blocked: Math.max(0, potential - creditable) };
  });
  const ready = farms.filter((f) => {
    const { ok, total } = readyCount(readiness(f, farmerById.get(f.farmer_id ?? "") ?? null, project));
    return ok === total;
  }).length;
  const area = farms.reduce((s, f) => s + Number(f.area_ha), 0);

  return (
    <>
      <PageHeader
        crumbs={[{ href: "/app/projects", label: "Projects" }]}
        title={project.name}
        description={`${PATHWAY_LABEL[project.pathway]} · ${project.methodology}${project.registry ? ` · ${project.registry}` : ""} · ${[project.region, project.country].filter(Boolean).join(", ")}`}
        actions={
          <>
            <ButtonLink href={`/app/projects/${project.id}/forecast`} variant="secondary">
              Forward sales
            </ButtonLink>
            <DownloadLink href={`/app/export/estimates.csv?project=${project.id}`}>
              <Download className="h-4 w-4" /> Estimates CSV
            </DownloadLink>
            {can.manage(ctx.role) && (
              <ButtonLink href={`/app/projects/${project.id}/edit`} variant="secondary">
                Edit
              </ButtonLink>
            )}
            {can.enrol(ctx.role) && (
              <ButtonLink href="/app/farms/new">
                <Plus className="h-4 w-4" /> Add farm
              </ButtonLink>
            )}
          </>
        }
      />
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Farms" value={farms.length} hint={`${ready} ready to credit`} />
        <Stat label="Area" value={fmt.ha(area)} />
        <Stat label="Creditable (all years)" value={fmt.t(chart.reduce((s, c) => s + c.creditable, 0))} />
        <Stat
          label="Blocked by paperwork"
          value={fmt.t(chart.reduce((s, c) => s + c.blocked, 0))}
          hint="unlocked by completing farm records"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          {farms.length > 0 && (
            <FarmMap
              farms={farms.map((f) => ({ id: f.id, name: f.name, boundary: f.boundary, status: f.status, area_ha: Number(f.area_ha) }))}
              className="h-80"
            />
          )}
          <Card>
            <CardHeader
              title="Estimated credits by year"
              description="Sum of each farm's latest estimate."
              action={
                can.manage(ctx.role) && (
                  <ActionForm
                    action={estimateProject}
                    submit="Estimate all farms"
                    variant="secondary"
                    hidden={{ project_id: project.id }}
                    className="items-end"
                  />
                )
              }
            />
            {chart.length ? (
              <div className="p-5">
                <YearBars
                  data={chart}
                  bars={[
                    { key: "creditable", label: "Creditable now", color: "var(--brand)", stack: "a" },
                    { key: "blocked", label: "Blocked by paperwork", color: "var(--accent)", stack: "a" },
                  ]}
                />
              </div>
            ) : (
              <EmptyState title="No estimates yet" body="Open a farm and run its estimate." />
            )}
          </Card>
        </div>
        <Card>
          <CardHeader title="Vintages" />
          {vintages.length ? (
            <Table className="[&_table]:min-w-0">
              <tbody>
                {vintages.map((v) => (
                  <tr key={v.id}>
                    <Td>
                      <Link href={`/app/credits/${v.id}`} className="font-medium hover:text-brand">
                        {v.year}
                      </Link>
                    </Td>
                    <Td className="tabular text-right">{fmt.t(v.net_t)}</Td>
                    <Td>
                      <Badge tone={VINTAGE_TONE[v.status]}>{VINTAGE_LABEL[v.status]}</Badge>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState title="No vintages yet" body="Prepare one from the Credits page." />
          )}
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Farms in this project" />
        {farms.length ? (
          <Table>
            <thead>
              <tr>
                <Th>Farm</Th>
                <Th>Farmer</Th>
                <Th className="text-right">Area</Th>
                <Th>Ready</Th>
              </tr>
            </thead>
            <tbody>
              {farms.map((f) => {
                const farmer = farmerById.get(f.farmer_id ?? "") ?? null;
                const { ok, total } = readyCount(readiness(f, farmer, project));
                return (
                  <tr key={f.id}>
                    <Td>
                      <Link href={`/app/farms/${f.id}`} className="font-medium hover:text-brand">
                        {f.name}
                      </Link>
                    </Td>
                    <Td>{farmer?.name ?? "—"}</Td>
                    <Td className="tabular text-right">{fmt.ha(f.area_ha)}</Td>
                    <Td>
                      <Badge tone={ok === total ? "brand" : "accent"}>
                        {ok}/{total}
                      </Badge>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        ) : (
          <EmptyState title="No farms in this project yet" />
        )}
      </Card>
    </>
  );
}
