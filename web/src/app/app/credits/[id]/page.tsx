import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/action-form";
import { Download } from "lucide-react";

import { Badge, Card, CardHeader, DownloadLink, EmptyState, Field, Input, Notice, PageHeader, Stat, Table, Td, Th } from "@/components/ui";
import { buildVintage, raisePayments, transitionVintage } from "@/lib/actions/credits";
import { getOrgContext, getProject, getVintage, listFarmers, listFarms, listPayments, memberNames } from "@/lib/data";
import type { VintageStatus } from "@/lib/database.types";
import { fmt, PAYMENT_TONE, VINTAGE_LABEL, VINTAGE_TONE } from "@/lib/format";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Vintage" };

type Derivation = {
  method?: string;
  farms?: { farm_id: string; farm?: string; net_t: number; gross_t: number; data_quality?: string }[];
  excluded?: { farm_id: string; status: string }[];
};

export default async function VintagePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ctx = await getOrgContext();
  const found = await getVintage(ctx.org.id, id);
  if (!found) notFound();
  const { vintage: v, events } = found;
  const [project, names, payments, farmers, farms] = await Promise.all([
    getProject(ctx.org.id, v.project_id),
    memberNames(ctx.org.id),
    listPayments(ctx.org.id, v.id),
    listFarmers(ctx.org.id),
    listFarms(ctx.org.id, { projectId: v.project_id }),
  ]);
  const farmerName = new Map(farmers.map((f) => [f.id, f.name]));
  const farmName = new Map(farms.map((f) => [f.id, f.name]));
  const d = v.derivation as Derivation;
  const own = v.submitted_by === ctx.user.id;

  const moves: { to: VintageStatus; label: string; allowed: boolean; note?: boolean; variant?: "secondary" | "danger" }[] = [];
  if (v.status === "draft" || v.status === "on_hold") moves.push({ to: "submitted", label: "Submit for review", allowed: can.manage(ctx.role) });
  if (v.status === "submitted") {
    moves.push({ to: "approved", label: "Approve", allowed: can.review(ctx.role) && !own, note: true });
    moves.push({ to: "on_hold", label: "Put on hold", allowed: can.review(ctx.role), note: true, variant: "secondary" });
  }
  if (v.status === "approved") moves.push({ to: "issued", label: `Issue ${v.issuable} credits`, allowed: can.administer(ctx.role) });

  return (
    <>
      <PageHeader
        crumbs={[{ href: "/app/credits", label: "Credits" }]}
        title={`${project?.name ?? "Project"} · ${v.year}`}
        description={`${project?.methodology ?? ""} · last change ${fmt.datetime(v.updated_at)}`}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={VINTAGE_TONE[v.status]}>{VINTAGE_LABEL[v.status]}</Badge>
            <DownloadLink href={`/app/export/vintage.csv?id=${v.id}`}>
              <Download className="h-4 w-4" /> Breakdown CSV
            </DownloadLink>
          </div>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Gross" value={fmt.t(v.gross_t, 2)} />
        <Stat label="Net" value={fmt.t(v.net_t, 2)} />
        <Stat label="Whole credits" value={fmt.int(v.issuable)} hint={`carry ${fmt.num(Number(v.net_t) - v.issuable, 3)} t`} tone="brand" />
        <Stat label="Serials" value={v.serial_start ? `${v.serial_start}–${v.serial_end}` : "—"} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader title="Where the tonnes come from" description={d.method} />
            {d.farms?.length ? (
              <Table>
                <thead>
                  <tr>
                    <Th>Farm</Th>
                    <Th className="text-right">Gross</Th>
                    <Th className="text-right">Net</Th>
                    <Th className="text-right">Share</Th>
                    <Th>Data</Th>
                  </tr>
                </thead>
                <tbody>
                  {d.farms
                    .slice()
                    .sort((a, b) => b.net_t - a.net_t)
                    .map((f) => (
                      <tr key={f.farm_id}>
                        <Td>
                          <Link href={`/app/farms/${f.farm_id}`} className="hover:text-brand">
                            {farmName.get(f.farm_id) ?? f.farm ?? f.farm_id.slice(0, 8)}
                          </Link>
                        </Td>
                        <Td className="tabular text-right">{fmt.num(f.gross_t, 3)}</Td>
                        <Td className="tabular text-right">
                          {f.net_t === 0 ? <Badge tone="accent">blocked</Badge> : fmt.num(f.net_t, 3)}
                        </Td>
                        <Td className="tabular text-right">{fmt.pct(Number(v.net_t) ? f.net_t / Number(v.net_t) : 0, 1)}</Td>
                        <Td className="text-xs text-muted">{f.data_quality}</Td>
                      </tr>
                    ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="No farm breakdown recorded" />
            )}
          </Card>

          {v.status === "issued" && (
            <Card>
              <CardHeader title="Farmer payments" description="Each farmer's share of the issued credits." />
              {payments.length ? (
                <Table>
                  <thead>
                    <tr>
                      <Th>Farmer</Th>
                      <Th className="text-right">Credits</Th>
                      <Th className="text-right">Amount</Th>
                      <Th>Status</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {payments.map((p) => (
                      <tr key={p.id}>
                        <Td>
                          <Link href={`/app/farmers/${p.farmer_id}`} className="hover:text-brand">
                            {farmerName.get(p.farmer_id) ?? "—"}
                          </Link>
                        </Td>
                        <Td className="tabular text-right">{fmt.num(p.credits, 3)}</Td>
                        <Td className="tabular text-right">{fmt.money(p.amount, p.currency)}</Td>
                        <Td>
                          <Badge tone={PAYMENT_TONE[p.status]}>{p.status}</Badge>
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              ) : can.administer(ctx.role) ? (
                <div className="p-5">
                  <ActionForm action={raisePayments} submit="Raise payments" hidden={{ vintage_id: v.id }}>
                    <div className="grid gap-4 sm:grid-cols-3">
                      <Field label="Price per credit">
                        <Input name="price" type="number" step="0.01" defaultValue={18} required />
                      </Field>
                      <Field label="Farmers' share (%)">
                        <Input name="share" type="number" step="1" defaultValue={60} required />
                      </Field>
                      <Field label="Currency">
                        <Input name="currency" defaultValue="USD" maxLength={3} />
                      </Field>
                    </div>
                  </ActionForm>
                </div>
              ) : (
                <EmptyState title="No payments raised yet" />
              )}
            </Card>
          )}
        </div>

        <div className="flex flex-col gap-6">
          {moves.length > 0 && (
            <Card>
              <CardHeader title="Next step" />
              <div className="flex flex-col gap-4 p-5">
                {own && v.status === "submitted" && (
                  <Notice tone="info">You submitted this vintage, so someone else has to approve it.</Notice>
                )}
                {!moves.some((m) => m.allowed) && (
                  <p className="text-sm text-muted">
                    Waiting on {v.status === "approved" ? "an owner or admin to issue it" : v.status === "submitted" ? "a reviewer" : "an analyst to submit it"}.
                  </p>
                )}
                {moves.filter((m) => m.allowed).map((m) => (
                  <ActionForm
                    key={m.to}
                    action={transitionVintage}
                    submit={m.label}
                    variant={m.variant ?? "primary"}
                    hidden={{ id: v.id, to: m.to }}
                  >
                    {m.note && (
                      <Field label={m.to === "on_hold" ? "Why (required)" : "Review note"}>
                        <Input name="note" required={m.to === "on_hold"} />
                      </Field>
                    )}
                  </ActionForm>
                ))}
                {v.status === "draft" && can.manage(ctx.role) && (
                  <ActionForm
                    action={buildVintage}
                    submit="Rebuild from latest estimates"
                    variant="secondary"
                    hidden={{ project_id: v.project_id, year: String(v.year) }}
                  />
                )}
              </div>
            </Card>
          )}
          <Card>
            <CardHeader title="History" />
            {events.length ? (
              <ol className="relative space-y-4 p-5 text-sm">
                {events.map((e) => (
                  <li key={e.id} className="border-l-2 border-border pl-3">
                    <div>
                      <Badge tone={VINTAGE_TONE[e.to_status]}>{VINTAGE_LABEL[e.to_status]}</Badge>{" "}
                      <span className="text-muted">by {names.get(e.actor ?? "") ?? "someone"}</span>
                    </div>
                    {e.note && <div className="mt-1">“{e.note}”</div>}
                    <div className="text-xs text-muted">{fmt.datetime(e.at)}</div>
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyState title="No changes yet" />
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
