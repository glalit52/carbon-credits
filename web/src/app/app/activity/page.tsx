import type { Metadata } from "next";

import { Badge, Card, EmptyState, PageHeader, Table, Td, Th } from "@/components/ui";
import { getOrgContext, listAudit, memberNames } from "@/lib/data";
import { fmt } from "@/lib/format";

export const metadata: Metadata = { title: "Activity" };

export default async function ActivityPage() {
  const ctx = await getOrgContext();
  const [events, names] = await Promise.all([listAudit(ctx.org.id, 300), memberNames(ctx.org.id)]);
  return (
    <>
      <PageHeader
        title="Activity"
        description="Every change to farms, farmers, projects, vintages, payments and members, written by the database itself. Nobody can edit or delete it, including admins."
      />
      <Card>
        {events.length === 0 ? (
          <EmptyState title="Nothing has happened yet" />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>When</Th>
                <Th>Who</Th>
                <Th>What</Th>
                <Th>Changed</Th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id}>
                  <Td className="whitespace-nowrap text-xs text-muted">{fmt.datetime(e.at)}</Td>
                  <Td>{names.get(e.actor ?? "") ?? <span className="text-muted">system</span>}</Td>
                  <Td>
                    <Badge tone={e.action === "delete" ? "danger" : e.action === "insert" ? "brand" : "info"}>{e.action}</Badge>{" "}
                    {e.entity}
                  </Td>
                  <Td className="max-w-md truncate font-mono text-xs text-muted">
                    {e.detail ? JSON.stringify(e.detail).slice(0, 160) : "—"}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
