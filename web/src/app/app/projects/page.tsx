import { Plus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { Badge, ButtonLink, Card, EmptyState, PageHeader } from "@/components/ui";
import { getOrgContext, listEstimates, listFarms, listProjects, listVintages } from "@/lib/data";
import { fmt, PATHWAY_LABEL } from "@/lib/format";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Projects" };

export default async function ProjectsPage() {
  const ctx = await getOrgContext();
  const [projects, farms, vintages, estimates] = await Promise.all([
    listProjects(ctx.org.id),
    listFarms(ctx.org.id),
    listVintages(ctx.org.id),
    listEstimates(ctx.org.id),
  ]);
  return (
    <>
      <PageHeader
        title="Projects"
        description="A project groups farms under one methodology, registry and crediting period."
        actions={
          can.manage(ctx.role) && (
            <ButtonLink href="/app/projects/new">
              <Plus className="h-4 w-4" /> New project
            </ButtonLink>
          )
        }
      />
      {projects.length === 0 ? (
        <Card>
          <EmptyState
            title="No projects yet"
            body="Start one for each pathway and region: rice methane in one delta, agroforestry in another."
            action={can.manage(ctx.role) && <ButtonLink href="/app/projects/new">Create a project</ButtonLink>}
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {projects.map((p) => {
            const own = farms.filter((f) => f.project_id === p.id);
            const ids = new Set(own.map((f) => f.id));
            const potential = estimates
              .filter((e) => ids.has(e.farm_id))
              .reduce(
                (s, e) =>
                  s + ((e.result as { vintages?: { potential?: { net_t: number } }[] }).vintages?.[0]?.potential?.net_t ?? 0),
                0,
              );
            const issued = vintages
              .filter((v) => v.project_id === p.id && v.status === "issued")
              .reduce((s, v) => s + v.issuable, 0);
            return (
              <Link key={p.id} href={`/app/projects/${p.id}`}>
                <Card className="h-full p-5 transition hover:border-brand">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="font-semibold">{p.name}</h2>
                      <p className="text-sm text-muted">
                        {PATHWAY_LABEL[p.pathway]} · {p.methodology}
                        {p.registry ? ` · ${p.registry}` : ""}
                      </p>
                    </div>
                    <Badge tone={p.status === "registered" ? "brand" : "neutral"}>{p.status}</Badge>
                  </div>
                  <dl className="mt-4 grid grid-cols-4 gap-2 text-sm">
                    <div>
                      <dt className="text-xs text-muted">Farms</dt>
                      <dd className="tabular font-medium">{own.length}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted">Area</dt>
                      <dd className="tabular font-medium">{fmt.ha(own.reduce((s, f) => s + Number(f.area_ha), 0))}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted">Potential</dt>
                      <dd className="tabular font-medium">{fmt.t(potential)}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted">Issued</dt>
                      <dd className="tabular font-medium">{fmt.int(issued)}</dd>
                    </div>
                  </dl>
                  <p className="mt-3 text-xs text-muted">{[p.region, p.country].filter(Boolean).join(", ")}</p>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
