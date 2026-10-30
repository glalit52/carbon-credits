import { Download, Plus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { Badge, ButtonLink, Card, DownloadLink, EmptyState, PageHeader, Table, Td, Th } from "@/components/ui";
import { getOrgContext, listFarmers, listFarms, listPayments } from "@/lib/data";
import { fmt } from "@/lib/format";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Farmers" };

export default async function FarmersPage() {
  const ctx = await getOrgContext();
  const [farmers, farms, payments] = await Promise.all([
    listFarmers(ctx.org.id),
    listFarms(ctx.org.id),
    listPayments(ctx.org.id),
  ]);
  return (
    <>
      <PageHeader
        title="Farmers"
        description="The people behind each farm: consent, carbon rights and what they have been paid."
        actions={
          <>
            <DownloadLink href="/app/export/farmers.csv">
              <Download className="h-4 w-4" /> CSV
            </DownloadLink>
            {can.enrol(ctx.role) && (
              <ButtonLink href="/app/farmers/new">
                <Plus className="h-4 w-4" /> Add farmer
              </ButtonLink>
            )}
          </>
        }
      />
      <Card>
        {farmers.length === 0 ? (
          <EmptyState title="No farmers yet" body="Farmers are added with their farms, by import, or here." />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Farmer</Th>
                <Th>Village</Th>
                <Th className="text-right">Farms</Th>
                <Th className="text-right">Area</Th>
                <Th>Consent</Th>
                <Th>Carbon rights</Th>
                <Th className="text-right">Paid</Th>
              </tr>
            </thead>
            <tbody>
              {farmers.map((f) => {
                const own = farms.filter((x) => x.farmer_id === f.id);
                const paid = payments
                  .filter((p) => p.farmer_id === f.id && p.status === "paid")
                  .reduce((s, p) => s + Number(p.amount), 0);
                return (
                  <tr key={f.id} className="hover:bg-surface-2/60">
                    <Td>
                      <Link href={`/app/farmers/${f.id}`} className="font-medium hover:text-brand">
                        {f.name}
                      </Link>
                      <div className="text-xs text-muted">{f.external_ref}</div>
                    </Td>
                    <Td className="text-muted">{[f.village, f.district].filter(Boolean).join(", ") || "—"}</Td>
                    <Td className="tabular text-right">{own.length}</Td>
                    <Td className="tabular text-right">{fmt.ha(own.reduce((s, x) => s + Number(x.area_ha), 0))}</Td>
                    <Td>{f.consent_on ? <Badge tone="brand">{fmt.date(f.consent_on)}</Badge> : <Badge tone="accent">missing</Badge>}</Td>
                    <Td>{f.carbon_rights_ref ? <Badge tone="brand">signed</Badge> : <Badge tone="accent">missing</Badge>}</Td>
                    <Td className="tabular text-right">{paid ? fmt.money(paid) : "—"}</Td>
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
