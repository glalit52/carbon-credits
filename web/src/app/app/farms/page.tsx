import { Download, Plus, Upload } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { FarmMap } from "@/components/map/farm-map";
import { Badge, ButtonLink, Card, DownloadLink, EmptyState, Input, PageHeader, Select, Table, Td, Th } from "@/components/ui";
import { getOrgContext, listEstimates, listFarmers, listFarms, listProjects } from "@/lib/data";
import { fmt, TENURE_LABEL } from "@/lib/format";
import { readiness, readyCount } from "@/lib/readiness";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Farms" };

export default async function FarmsPage({
  searchParams,
}: {
  searchParams: Promise<{ project?: string; status?: string; q?: string }>;
}) {
  const { project, status, q } = await searchParams;
  const ctx = await getOrgContext();
  const [farms, farmers, projects, estimates] = await Promise.all([
    listFarms(ctx.org.id, { projectId: project }),
    listFarmers(ctx.org.id),
    listProjects(ctx.org.id),
    listEstimates(ctx.org.id),
  ]);
  const farmerById = new Map(farmers.map((f) => [f.id, f]));
  const projectById = new Map(projects.map((p) => [p.id, p]));
  const needle = q?.toLowerCase().trim();
  const shown = farms.filter(
    (f) =>
      (!status || f.status === status) &&
      (!needle ||
        f.name.toLowerCase().includes(needle) ||
        f.external_ref?.toLowerCase().includes(needle) ||
        farmerById.get(f.farmer_id ?? "")?.name.toLowerCase().includes(needle)),
  );
  const potentialByFarm = new Map<string, number>();
  for (const e of estimates) {
    const potential = (e.result as { vintages?: { potential?: { net_t: number } }[] })?.vintages?.[0]?.potential?.net_t ?? 0;
    potentialByFarm.set(e.farm_id, (potentialByFarm.get(e.farm_id) ?? 0) + potential);
  }
  const totalHa = shown.reduce((s, f) => s + Number(f.area_ha), 0);

  return (
    <>
      <PageHeader
        title="Farms"
        description={`${shown.length} farms · ${fmt.ha(totalHa)}`}
        actions={
          <>
            <DownloadLink href={`/app/export/farms.csv${project ? `?project=${project}` : ""}`}>
              <Download className="h-4 w-4" /> CSV
            </DownloadLink>
            <DownloadLink href={`/app/export/farms.geojson${project ? `?project=${project}` : ""}`}>
              <Download className="h-4 w-4" /> GeoJSON
            </DownloadLink>
            {can.enrol(ctx.role) && (
            <>
              <ButtonLink href="/app/import" variant="secondary">
                <Upload className="h-4 w-4" /> Import
              </ButtonLink>
              <ButtonLink href="/app/farms/new">
                <Plus className="h-4 w-4" /> Add farm
              </ButtonLink>
            </>
            )}
          </>
        }
      />

      {farms.length === 0 ? (
        <Card>
          <EmptyState
            title="No farms yet"
            body="Draw a boundary on the map, walk it with GPS, or import the farms you already have from a spreadsheet, KML or GeoJSON."
            action={
              can.enrol(ctx.role) && (
                <div className="flex gap-2">
                  <ButtonLink href="/app/farms/new">Add a farm</ButtonLink>
                  <ButtonLink href="/app/import" variant="secondary">
                    Import farms
                  </ButtonLink>
                </div>
              )
            }
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-6">
          <FarmMap
            farms={shown.map((f) => ({ id: f.id, name: f.name, boundary: f.boundary, status: f.status, area_ha: Number(f.area_ha) }))}
            className="h-80 lg:h-96"
          />

          <Card>
            <form className="flex flex-wrap gap-2 border-b border-border p-3">
              <Input name="q" defaultValue={q} placeholder="Search farm, reference or farmer" className="max-w-xs" />
              <Select name="project" defaultValue={project ?? ""} className="max-w-xs">
                <option value="">All projects</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
              <Select name="status" defaultValue={status ?? ""} className="max-w-[10rem]">
                <option value="">Any status</option>
                <option value="enrolled">Enrolled</option>
                <option value="draft">Draft</option>
                <option value="blocked">Blocked</option>
                <option value="withdrawn">Withdrawn</option>
              </Select>
              <button className="rounded-lg border border-border px-3 text-sm hover:bg-surface-2">Filter</button>
            </form>
            <Table>
              <thead>
                <tr>
                  <Th>Farm</Th>
                  <Th>Farmer</Th>
                  <Th>Project</Th>
                  <Th className="text-right">Area</Th>
                  <Th>Tenure</Th>
                  <Th>Ready</Th>
                  <Th className="text-right">Potential (net)</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {shown.map((f) => {
                  const farmer = farmerById.get(f.farmer_id ?? "") ?? null;
                  const proj = projectById.get(f.project_id ?? "") ?? null;
                  const { ok, total } = readyCount(readiness(f, farmer, proj));
                  return (
                    <tr key={f.id} className="hover:bg-surface-2/60">
                      <Td>
                        <Link href={`/app/farms/${f.id}`} className="font-medium hover:text-brand">
                          {f.name}
                        </Link>
                        <div className="text-xs text-muted">{f.external_ref}</div>
                      </Td>
                      <Td>{farmer?.name ?? <span className="text-muted">—</span>}</Td>
                      <Td className="text-muted">{proj?.name ?? "—"}</Td>
                      <Td className="tabular text-right">{fmt.ha(f.area_ha)}</Td>
                      <Td className="text-xs">
                        {f.tenure ? TENURE_LABEL[f.tenure] : "—"}
                        {f.tenure && !f.tenure_reference && <div className="text-accent">no document</div>}
                      </Td>
                      <Td>
                        <Badge tone={ok === total ? "brand" : "accent"}>
                          {ok}/{total}
                        </Badge>
                      </Td>
                      <Td className="tabular text-right">{potentialByFarm.has(f.id) ? fmt.t(potentialByFarm.get(f.id)) : "—"}</Td>
                      <Td>
                        <Badge tone={f.status === "enrolled" ? "brand" : f.status === "draft" ? "accent" : "danger"}>{f.status}</Badge>
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
