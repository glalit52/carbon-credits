import type { Metadata } from "next";
import Link from "next/link";

import { Download } from "lucide-react";

import { Badge, Card, DownloadLink, EmptyState, PageHeader, Stat, Table, Td, Th } from "@/components/ui";
import { setPaymentStatus } from "@/lib/actions/credits";
import { getOrgContext, listFarmers, listPayments, listProjects, listVintages } from "@/lib/data";
import { fmt, PAYMENT_TONE } from "@/lib/format";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Payments" };

export default async function PaymentsPage() {
  const ctx = await getOrgContext();
  const [payments, farmers, vintages, projects] = await Promise.all([
    listPayments(ctx.org.id),
    listFarmers(ctx.org.id),
    listVintages(ctx.org.id),
    listProjects(ctx.org.id),
  ]);
  const farmer = new Map(farmers.map((f) => [f.id, f]));
  const vintage = new Map(vintages.map((v) => [v.id, v]));
  const project = new Map(projects.map((p) => [p.id, p.name]));
  const sum = (s: string) => payments.filter((p) => p.status === s).reduce((a, p) => a + Number(p.amount), 0);
  const currency = payments[0]?.currency ?? "USD";
  const today = new Date().toISOString().slice(0, 10);
  const overdue = payments.filter((p) => p.status !== "paid" && p.due_on && p.due_on < today);

  return (
    <>
      <PageHeader
        title="Payments"
        description="What each farmer is owed from issued credits, and what has reached them."
        actions={
          <DownloadLink href="/app/export/payments.csv">
            <Download className="h-4 w-4" /> CSV
          </DownloadLink>
        }
      />
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Paid" value={fmt.money(sum("paid"), currency)} tone="brand" />
        <Stat label="Approved, not paid" value={fmt.money(sum("approved"), currency)} />
        <Stat label="Pending approval" value={fmt.money(sum("pending"), currency)} />
        <Stat label="Overdue" value={overdue.length} hint={overdue.length ? "past due date and unpaid" : "none"} />
      </div>
      <Card>
        {payments.length === 0 ? (
          <EmptyState title="No payments yet" body="Payments are raised from an issued vintage." />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Farmer</Th>
                <Th>Vintage</Th>
                <Th className="text-right">Credits</Th>
                <Th className="text-right">Amount</Th>
                <Th>Due</Th>
                <Th>Status</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {payments.map((p) => {
                const v = vintage.get(p.vintage_id);
                const f = farmer.get(p.farmer_id);
                return (
                  <tr key={p.id}>
                    <Td>
                      <Link href={`/app/farmers/${p.farmer_id}`} className="font-medium hover:text-brand">
                        {f?.name ?? "—"}
                      </Link>
                      <div className="text-xs text-muted">
                        {f?.payout_method} {f?.payout_reference}
                      </div>
                    </Td>
                    <Td>
                      {v ? (
                        <Link href={`/app/credits/${v.id}`} className="hover:text-brand">
                          {project.get(v.project_id)} · {v.year}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </Td>
                    <Td className="tabular text-right">{fmt.num(p.credits, 3)}</Td>
                    <Td className="tabular text-right">{fmt.money(p.amount, p.currency)}</Td>
                    <Td className="text-xs">
                      {fmt.date(p.due_on)}
                      {p.paid_on && <div className="text-muted">paid {fmt.date(p.paid_on)}</div>}
                    </Td>
                    <Td>
                      <Badge tone={PAYMENT_TONE[p.status]}>{p.status}</Badge>
                      {p.reference && <div className="text-xs text-muted">{p.reference}</div>}
                    </Td>
                    <Td className="text-right">
                      {can.administer(ctx.role) && p.status !== "paid" && (
                        <form action={setPaymentStatus} className="flex justify-end gap-2">
                          <input type="hidden" name="id" value={p.id} />
                          {p.status === "pending" ? (
                            <button name="status" value="approved" className="text-xs text-brand hover:underline" disabled={ctx.demo}>
                              Approve
                            </button>
                          ) : (
                            <>
                              <input
                                name="reference"
                                placeholder="UTR / txn id"
                                className="w-28 rounded border border-border bg-surface px-2 py-1 text-xs"
                              />
                              <button name="status" value="paid" className="text-xs text-brand hover:underline" disabled={ctx.demo}>
                                Mark paid
                              </button>
                            </>
                          )}
                        </form>
                      )}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
