import { CheckCircle2, CircleAlert, Paperclip } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/action-form";
import { RainBars, YearBars } from "@/components/charts";
import { FarmMap } from "@/components/map/farm-map";
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Input,
  Notice,
  PageHeader,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { addPractice, addSoilSample, deleteFarm, estimateFarm, updateFarmStatus } from "@/lib/actions/farms";
import {
  getFarm,
  getFarmer,
  getOrgContext,
  getProject,
  listEstimates,
  listPractices,
  listSoil,
} from "@/lib/data";
import type { EngineResult } from "@/lib/engine";
import { fmt, MONTHS, PATHWAY_LABEL, TENURE_LABEL } from "@/lib/format";
import { readiness } from "@/lib/readiness";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Farm" };

function md(month: number, day: number) {
  return `${day} ${MONTHS[month - 1]}`;
}

export default async function FarmPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ created?: string; saved?: string }>;
}) {
  const [{ id }, { created, saved }] = await Promise.all([params, searchParams]);
  const ctx = await getOrgContext();
  const farm = await getFarm(ctx.org.id, id);
  if (!farm) notFound();
  const [farmer, project, estimates, practices, soil] = await Promise.all([
    farm.farmer_id ? getFarmer(ctx.org.id, farm.farmer_id) : null,
    farm.project_id ? getProject(ctx.org.id, farm.project_id) : null,
    listEstimates(ctx.org.id, farm.id),
    listPractices(ctx.org.id, farm.id),
    listSoil(ctx.org.id, farm.id),
  ]);
  const checks = readiness(farm, farmer, project);
  const latest = estimates.at(-1);
  const result = latest?.result as unknown as EngineResult | undefined;
  const chart = estimates.map((e) => {
    const v = (e.result as unknown as EngineResult).vintages[0];
    return {
      year: e.year,
      creditable: Number(e.net_t),
      blocked: Math.max(0, (v.potential?.net_t ?? 0) - Number(e.net_t)),
    };
  });
  const latestVintage = result?.vintages[0];

  return (
    <>
      <PageHeader
        crumbs={[{ href: "/app/farms", label: "Farms" }]}
        title={farm.name}
        description={
          <>
            {farm.external_ref && <span className="mr-2">{farm.external_ref}</span>}
            {project ? (
              <Link href={`/app/projects/${project.id}`} className="underline">
                {project.name}
              </Link>
            ) : (
              "Not in a project"
            )}
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={farm.status === "enrolled" ? "brand" : farm.status === "draft" ? "accent" : "danger"}>{farm.status}</Badge>
            <ButtonLink href={`/app/farms/${farm.id}/monitoring`} variant="secondary">
              Monitoring
            </ButtonLink>
            {can.enrol(ctx.role) && (
              <>
                <ButtonLink href={`/app/farms/${farm.id}/edit`} variant="secondary">
                  Edit
                </ButtonLink>
                <ActionForm action={estimateFarm} submit="Run estimate" hidden={{ farm_id: farm.id }} className="flex-row" />
              </>
            )}
          </div>
        }
      />
      {saved && (
        <div className="mb-6">
          <Notice tone="brand">Changes saved. Run the estimate again if the boundary, calendar or eligibility changed.</Notice>
        </div>
      )}
      {created && (
        <div className="mb-6">
          <Notice tone="brand" title="Farm saved">
            Run an estimate to see what it can earn, and work through the checklist to make it creditable.
          </Notice>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <FarmMap
            farms={[{ id: farm.id, name: farm.name, boundary: farm.boundary, status: farm.status, area_ha: Number(farm.area_ha) }]}
            linkBase={null}
            className="h-80"
          />

          <Card>
            <CardHeader
              title="Credit estimate"
              description={
                result
                  ? `${result.methodology} · ${result.data_quality} · run ${fmt.datetime(latest!.created_at)}`
                  : "Not estimated yet."
              }
            />
            {!result ? (
              <EmptyState
                title="No estimate yet"
                body={
                  project
                    ? "Run the engine to quantify this farm on its own climate and crop calendar."
                    : "Add the farm to a project first; the project decides the methodology."
                }
              />
            ) : (
              <div className="flex flex-col gap-5 p-5">
                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <div className="text-xs uppercase tracking-wide text-muted">Creditable now</div>
                    <div className="tabular text-2xl font-semibold">{fmt.t(estimates.reduce((s, e) => s + Number(e.net_t), 0), 2)}</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-wide text-muted">Potential</div>
                    <div className="tabular text-2xl font-semibold text-brand">
                      {fmt.t(chart.reduce((s, c) => s + c.creditable + c.blocked, 0), 2)}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-wide text-muted">Per hectare (latest year)</div>
                    <div className="tabular text-2xl font-semibold">
                      {fmt.num((latestVintage?.potential?.net_t ?? 0) / Number(farm.area_ha), 2)} t/ha
                    </div>
                  </div>
                </div>
                <YearBars
                  data={chart}
                  bars={[
                    { key: "creditable", label: "Creditable now", color: "var(--brand)", stack: "a" },
                    { key: "blocked", label: "Blocked by paperwork", color: "var(--accent)", stack: "a" },
                  ]}
                />
                {result.blockers.length > 0 && (
                  <Notice tone="accent" title="What blocks crediting">
                    <ul className="list-disc pl-4">
                      {result.blockers.map((b) => (
                        <li key={b}>{b}</li>
                      ))}
                    </ul>
                  </Notice>
                )}
                {latestVintage?.deductions && (
                  <div>
                    <h3 className="mb-2 text-sm font-semibold">Latest year, from gross to net ({latestVintage.year})</h3>
                    <dl className="divide-y divide-border rounded-lg border border-border text-sm">
                      <div className="flex justify-between px-3 py-2">
                        <dt>Gross</dt>
                        <dd className="tabular">{fmt.t(latestVintage.potential?.gross_t ?? latestVintage.gross_t, 3)}</dd>
                      </div>
                      {latestVintage.deductions.map((d) => (
                        <div key={d.name} className="flex justify-between gap-4 px-3 py-2">
                          <dt>
                            − {d.name} <span className="text-xs text-muted">({d.basis})</span>
                          </dt>
                          <dd className="tabular">{fmt.pct(d.fraction, 1)}</dd>
                        </div>
                      ))}
                      <div className="flex justify-between px-3 py-2 font-medium">
                        <dt>Net (potential)</dt>
                        <dd className="tabular">{fmt.t(latestVintage.potential?.net_t, 3)}</dd>
                      </div>
                    </dl>
                  </div>
                )}
                {result.site.assumptions.length > 0 && (
                  <div>
                    <h3 className="mb-2 text-sm font-semibold">Generic inputs (replace with local data to tighten)</h3>
                    <ul className="space-y-1 text-sm">
                      {result.site.assumptions.map((a) => (
                        <li key={a.parameter}>
                          <code className="text-xs">{a.parameter}</code> = <strong>{String(a.value)}</strong>
                          <span className="text-muted"> — {a.basis}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <h3 className="mb-1 text-sm font-semibold">Climate</h3>
                    <p className="text-xs text-muted">
                      {result.site.climate.source} · mean {fmt.num(result.site.climate.mean_temp_c, 1)} °C ·{" "}
                      {fmt.int(result.site.climate.monthly_rain_mm.reduce((a, b) => a + b, 0))} mm/yr
                    </p>
                    <RainBars rain={result.site.climate.monthly_rain_mm} />
                  </div>
                  <div className="text-xs text-muted">
                    <h3 className="mb-1 text-sm font-semibold text-text">Notes</h3>
                    <ul className="list-disc space-y-1 pl-4">
                      {result.notes.map((n) => (
                        <li key={n}>{n}</li>
                      ))}
                      {latestVintage?.warnings?.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  </div>
                </div>
                {latestVintage?.calculations && (
                  <details className="text-sm">
                    <summary className="cursor-pointer font-medium">Full derivation ({latestVintage.calculations.length} steps)</summary>
                    <pre className="mt-2 max-h-96 overflow-auto rounded-lg bg-surface-2 p-3 text-xs">
                      {JSON.stringify(latestVintage.calculations, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            )}
          </Card>

          <Card>
            <CardHeader title="Practice records" description="What was done on this farm, season by season, with evidence." />
            {practices.length > 0 ? (
              <Table>
                <thead>
                  <tr>
                    <Th>Year</Th>
                    <Th>Season</Th>
                    <Th>Practice</Th>
                    <Th>Dates</Th>
                    <Th>Notes</Th>
                  </tr>
                </thead>
                <tbody>
                  {practices.map((p) => (
                    <tr key={p.id}>
                      <Td>{p.year}</Td>
                      <Td>{p.season ?? "—"}</Td>
                      <Td>
                        <Badge tone="info">{p.practice}</Badge>
                      </Td>
                      <Td className="text-xs text-muted">
                        {fmt.date(p.started_on)} – {fmt.date(p.ended_on)}
                      </Td>
                      <Td className="text-xs">
                        {p.notes}
                        {p.evidence_path && (
                          <a
                            href={`/app/evidence?path=${encodeURIComponent(p.evidence_path)}`}
                            target="_blank"
                            rel="noreferrer"
                            className="ml-1 inline-flex items-center gap-0.5 text-brand hover:underline"
                          >
                            <Paperclip className="h-3 w-3" /> evidence
                          </a>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="Nothing recorded yet" />
            )}
            {can.enrol(ctx.role) && (
              <details className="border-t border-border p-5">
                <summary className="cursor-pointer text-sm font-medium text-brand">Record a practice</summary>
                <ActionForm action={addPractice} submit="Save record" variant="secondary" className="mt-4" hidden={{ farm_id: farm.id }}>
                  <div className="grid gap-4 sm:grid-cols-3">
                    <Field label="Year">
                      <Input name="year" type="number" defaultValue={new Date().getFullYear()} required />
                    </Field>
                    <Field label="Season">
                      <Input name="season" placeholder={farm.seasons?.[0]?.name ?? "Kharif"} />
                    </Field>
                    <Field label="Practice">
                      <Input name="practice" defaultValue={farm.practice ?? ""} required />
                    </Field>
                    <Field label="Started">
                      <Input name="started_on" type="date" />
                    </Field>
                    <Field label="Ended">
                      <Input name="ended_on" type="date" />
                    </Field>
                    <Field label="Evidence" hint="Photo, log sheet or PDF, under 20 MB.">
                      <Input name="evidence" type="file" accept="image/*,application/pdf" capture="environment" />
                    </Field>
                  </div>
                  <Field label="Notes">
                    <Input name="notes" placeholder="e.g. 3 dry-downs observed at the field tube" />
                  </Field>
                </ActionForm>
              </details>
            )}
          </Card>

          <Card>
            <CardHeader title="Soil samples" description="Lab results by depth. Bulk density lets stocks be compared on equivalent soil mass." />
            {soil.length > 0 ? (
              <Table>
                <thead>
                  <tr>
                    <Th>Sampled</Th>
                    <Th>Depth</Th>
                    <Th className="text-right">SOC</Th>
                    <Th className="text-right">Bulk density</Th>
                    <Th>Lab</Th>
                  </tr>
                </thead>
                <tbody>
                  {soil.map((s) => (
                    <tr key={s.id}>
                      <Td>{fmt.date(s.sampled_on)}</Td>
                      <Td>
                        {s.depth_top_cm}–{s.depth_bottom_cm} cm
                      </Td>
                      <Td className="tabular text-right">{fmt.num(s.soc_pct, 2)} %</Td>
                      <Td className="tabular text-right">{s.bulk_density ? `${fmt.num(s.bulk_density, 2)} g/cm³` : "—"}</Td>
                      <Td className="text-xs text-muted">
                        {s.lab} {s.lab_reference}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="No samples yet" />
            )}
            {can.enrol(ctx.role) && (
              <details className="border-t border-border p-5">
                <summary className="cursor-pointer text-sm font-medium text-brand">Add a sample</summary>
                <ActionForm action={addSoilSample} submit="Save sample" variant="secondary" className="mt-4" hidden={{ farm_id: farm.id }}>
                  <div className="grid gap-4 sm:grid-cols-4">
                    <Field label="Sampled on">
                      <Input name="sampled_on" type="date" required />
                    </Field>
                    <Field label="Top (cm)">
                      <Input name="depth_top_cm" type="number" step="0.1" defaultValue={0} required />
                    </Field>
                    <Field label="Bottom (cm)">
                      <Input name="depth_bottom_cm" type="number" step="0.1" defaultValue={30} required />
                    </Field>
                    <Field label="SOC (%)">
                      <Input name="soc_pct" type="number" step="0.001" required />
                    </Field>
                    <Field label="Bulk density (g/cm³)">
                      <Input name="bulk_density" type="number" step="0.001" />
                    </Field>
                    <Field label="Lab">
                      <Input name="lab" />
                    </Field>
                    <Field label="Lab reference">
                      <Input name="lab_reference" />
                    </Field>
                  </div>
                </ActionForm>
              </details>
            )}
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader title="Ready to credit?" description={`${checks.filter((c) => c.ok).length} of ${checks.length} done`} />
            <ul className="divide-y divide-border">
              {checks.map((c) => (
                <li key={c.label} className="flex gap-3 px-5 py-3 text-sm">
                  {c.ok ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
                  ) : (
                    <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                  )}
                  <div>
                    <div className={c.ok ? "" : "font-medium"}>{c.label}</div>
                    {!c.ok && <div className="text-xs text-muted">{c.fix}</div>}
                    {!c.ok && can.enrol(ctx.role) && (c.on === "farm" || farmer) && (
                      <Link
                        href={c.on === "farm" ? `/app/farms/${farm.id}/edit` : `/app/farmers/${farmer!.id}/edit`}
                        className="text-xs font-medium text-brand"
                      >
                        Fix it →
                      </Link>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title="Details" />
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 p-5 text-sm">
              <dt className="text-muted">Area</dt>
              <dd className="tabular">{fmt.ha(farm.area_ha)}</dd>
              <dt className="text-muted">Centre</dt>
              <dd className="tabular">
                {farm.centroid_lat.toFixed(5)}, {farm.centroid_lon.toFixed(5)}
              </dd>
              <dt className="text-muted">Pathway</dt>
              <dd>{project ? PATHWAY_LABEL[project.pathway] : "—"}</dd>
              <dt className="text-muted">Crop</dt>
              <dd>{farm.crop ?? "—"}</dd>
              <dt className="text-muted">Practice</dt>
              <dd>{farm.practice ?? "—"}</dd>
              <dt className="text-muted">Enrolled</dt>
              <dd>{fmt.date(farm.enrolled_on)}</dd>
              <dt className="text-muted">Tenure</dt>
              <dd>
                {farm.tenure ? TENURE_LABEL[farm.tenure] : "—"}
                {farm.tenure_reference && <div className="text-xs text-muted">{farm.tenure_reference}</div>}
              </dd>
              {farm.seasons?.length > 0 && (
                <>
                  <dt className="text-muted">Seasons</dt>
                  <dd>
                    {farm.seasons.map((s) => (
                      <div key={s.name}>
                        {s.name}: {md(s.start_month, s.start_day)} – {md(s.end_month, s.end_day)}
                      </div>
                    ))}
                  </dd>
                </>
              )}
              {farm.species?.length ? (
                <>
                  <dt className="text-muted">Species</dt>
                  <dd>{farm.species.join(", ")}</dd>
                </>
              ) : null}
              <dt className="text-muted">Boundary</dt>
              <dd>{farm.source}</dd>
            </dl>
          </Card>

          <Card>
            <CardHeader title="Farmer" />
            {farmer ? (
              <div className="p-5 text-sm">
                <Link href={`/app/farmers/${farmer.id}`} className="font-medium hover:text-brand">
                  {farmer.name}
                </Link>
                <div className="text-muted">
                  {[farmer.village, farmer.district].filter(Boolean).join(", ")}
                </div>
                <div className="mt-2 text-xs text-muted">
                  Consent {farmer.consent_on ? `signed ${fmt.date(farmer.consent_on)}` : "not recorded"}
                </div>
              </div>
            ) : (
              <EmptyState title="No farmer linked" />
            )}
          </Card>

          {can.manage(ctx.role) && (
            <Card>
              <CardHeader title="Manage" />
              <div className="flex flex-wrap gap-2 p-5">
                {farm.status !== "withdrawn" ? (
                  <form action={updateFarmStatus}>
                    <input type="hidden" name="id" value={farm.id} />
                    <input type="hidden" name="status" value="withdrawn" />
                    <Button variant="secondary" disabled={ctx.demo}>
                      Withdraw farm
                    </Button>
                  </form>
                ) : (
                  <form action={updateFarmStatus}>
                    <input type="hidden" name="id" value={farm.id} />
                    <input type="hidden" name="status" value="enrolled" />
                    <Button variant="secondary" disabled={ctx.demo}>
                      Re-enrol
                    </Button>
                  </form>
                )}
                <form action={deleteFarm}>
                  <input type="hidden" name="id" value={farm.id} />
                  <Button variant="ghost" className="text-danger" disabled={ctx.demo}>
                    Delete
                  </Button>
                </form>
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
