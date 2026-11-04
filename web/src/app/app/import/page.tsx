import type { Metadata } from "next";

import { Importer } from "@/components/importer";
import { Badge, Card, CardHeader, Notice, PageHeader, Table, Td, Th } from "@/components/ui";
import { getOrgContext, listImports, listProjects } from "@/lib/data";
import { fmt } from "@/lib/format";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Import data" };

export default async function ImportPage() {
  const ctx = await getOrgContext();
  const [projects, runs] = await Promise.all([listProjects(ctx.org.id), listImports(ctx.org.id)]);
  return (
    <>
      <PageHeader
        title="Import existing data"
        description="Bring in the farms, farmers, practice logs and lab results you already have. Every row is checked and shown to you before anything is written; rows with problems are skipped, never half-saved."
      />
      {!can.enrol(ctx.role) ? (
        <Notice tone="accent">Your role is read-only. Ask an admin for field agent or analyst access to import.</Notice>
      ) : (
        <Importer projects={projects} readOnly={ctx.demo} />
      )}
      {runs.length > 0 && (
        <Card className="mt-6">
          <CardHeader title="Recent imports" />
          <Table>
            <thead>
              <tr>
                <Th>When</Th>
                <Th>What</Th>
                <Th>File</Th>
                <Th className="text-right">Imported</Th>
                <Th className="text-right">Skipped</Th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <Td className="text-muted">{fmt.datetime(r.created_at)}</Td>
                  <Td>
                    <Badge>{r.kind}</Badge>
                  </Td>
                  <Td>{r.filename}</Td>
                  <Td className="tabular text-right">{r.ok_count}</Td>
                  <Td className="tabular text-right">{r.error_count}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}
    </>
  );
}
