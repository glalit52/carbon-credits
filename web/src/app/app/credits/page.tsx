import type { Metadata } from "next";
import Link from "next/link";

import { ActionForm } from "@/components/action-form";
import { Badge, Card, CardHeader, EmptyState, Field, Input, PageHeader, Select, Stat, Table, Td, Th } from "@/components/ui";
import { buildVintage } from "@/lib/actions/credits";
import { getOrgContext, listProjects, listVintages } from "@/lib/data";
import type { VintageStatus } from "@/lib/database.types";
import { fmt, VINTAGE_LABEL, VINTAGE_TONE } from "@/lib/format";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Credits" };

const PIPELINE: VintageStatus[] = ["draft", "submitted", "on_hold", "approved", "issued"];

export default async function CreditsPage() {
  const ctx = await getOrgContext();
  const [vintages, projects] = await Promise.all([listVintages(ctx.org.id), listProjects(ctx.org.id)]);
  const projectName = new Map(projects.map((p) => [p.id, p.name]));
  const waiting = vintages.filter((v) => v.status === "submitted" && v.submitted_by !== ctx.user.id);

  return (
    <>
      <PageHeader
        title="Credits"
        description="Vintages move from draft to review to approval to issuance. A second person approves every one, and every step is logged."
      />

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
        {PIPELINE.map((s) => {
          const vs = vintages.filter((v) => v.status === s);
          return (
            <Stat
              key={s}
              label={VINTAGE_LABEL[s]}
              value={vs.length}
              hint={s === "issued" ? `${fmt.int(vs.reduce((a, v) => a + v.issuable, 0))} credits` : fmt.t(vs.reduce((a, v) => a + Number(v.net_t), 0))}
            />
          );
        })}
      </div>

      {can.review(ctx.role) && waiting.length > 0 && (
        <Card className="mb-6 border-info">
          <CardHeader title="Waiting for your review" description="Submitted by someone else, so you can approve them." />
          <ul className="divide-y divide-border">
            {waiting.map((v) => (
              <li key={v.id}>
                <Link href={`/app/credits/${v.id}`} className="flex items-center justify-between px-5 py-3 text-sm hover:bg-surface-2">
                  <span>
                    <strong>{projectName.get(v.project_id)}</strong> · {v.year}
                  </span>
                  <span className="tabular">{fmt.t(v.net_t, 2)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Vintages" />
          {vintages.length === 0 ? (
            <EmptyState title="No vintages yet" body="Estimate your farms, then prepare a vintage for a project and year." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Project</Th>
                  <Th>Year</Th>
                  <Th className="text-right">Gross</Th>
                  <Th className="text-right">Net</Th>
                  <Th className="text-right">Credits</Th>
                  <Th>Status</Th>
                  <Th>Serials</Th>
                </tr>
              </thead>
              <tbody>
                {vintages.map((v) => (
                  <tr key={v.id} className="hover:bg-surface-2/60">
                    <Td>
                      <Link href={`/app/credits/${v.id}`} className="font-medium hover:text-brand">
                        {projectName.get(v.project_id) ?? "—"}
                      </Link>
                    </Td>
                    <Td>{v.year}</Td>
                    <Td className="tabular text-right">{fmt.t(v.gross_t, 2)}</Td>
                    <Td className="tabular text-right">{fmt.t(v.net_t, 2)}</Td>
                    <Td className="tabular text-right">{fmt.int(v.issuable)}</Td>
                    <Td>
                      <Badge tone={VINTAGE_TONE[v.status]}>{VINTAGE_LABEL[v.status]}</Badge>
                    </Td>
                    <Td className="tabular text-xs text-muted">
                      {v.serial_start ? `${v.serial_start}–${v.serial_end}` : "—"}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>

        {can.manage(ctx.role) && (
          <Card>
            <CardHeader title="Prepare a vintage" description="Sums the latest estimate of every enrolled farm in the project." />
            <div className="p-5">
              <ActionForm action={buildVintage} submit="Build draft vintage">
                <Field label="Project">
                  <Select name="project_id" required>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Year">
                  <Input name="year" type="number" defaultValue={new Date().getFullYear() - 1} required />
                </Field>
              </ActionForm>
            </div>
          </Card>
        )}
      </div>
    </>
  );
}
