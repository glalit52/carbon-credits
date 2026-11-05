import {
  ExternalLink,
  FolderLock,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { Badge, ButtonLink, Card, CardHeader, EmptyState, PageHeader, Stat, Table, Td, Th } from "@/components/ui";
import { getOrgContext, listProjects, listVintages } from "@/lib/data";
import { fmt, VINTAGE_LABEL, VINTAGE_TONE } from "@/lib/format";

export const metadata: Metadata = { title: "Credit Registry & Portfolio" };

export default async function PortfolioPage() {
  const ctx = await getOrgContext();
  const [projects, vintages] = await Promise.all([
    listProjects(ctx.org.id),
    listVintages(ctx.org.id),
  ]);

  const issuedVintages = vintages.filter((v) => v.status === "issued");
  const totalIssued = issuedVintages.reduce((sum, v) => sum + v.issuable, 0);
  const totalInReview = vintages
    .filter((v) => v.status === "submitted" || v.status === "approved")
    .reduce((sum, v) => sum + v.issuable, 0);

  return (
    <>
      <PageHeader
        title="Credit Registry & Portfolio Explorer"
        crumbs={[{ href: "/app", label: "App" }, { href: "/app/portfolio", label: "Portfolio" }]}
        description="Unified registry ledger tracking serialized carbon credit issuances, non-permanence buffer reserves, Article 6 authorizations, and buyer retirements."
        actions={
          <div className="flex items-center gap-2">
            <ButtonLink href="/app/credits/registry" variant="secondary" className="text-xs">
              <ExternalLink className="h-3.5 w-3.5" /> Reconcile with Verra / GS
            </ButtonLink>
          </div>
        }
      />

      {/* Registry Top Stats */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Total Issued Credits"
          value={<span className="text-brand">{fmt.int(totalIssued)} tCO₂e</span>}
          hint="Minted & serialized on immutable log"
          tone="brand"
        />
        <Stat
          label="In Review (4-Eyes)"
          value={`${fmt.int(totalInReview)} tCO₂e`}
          hint="Under VVB & second approver check"
        />
        <Stat
          label="Buffer Pool Reserve"
          value={`${fmt.int(Math.round(totalIssued * 0.15))} tCO₂e`}
          hint="Non-permanence pooled risk reserve"
        />
        <Stat
          label="Registry Standards"
          value="VCS · CORSIA"
          hint="VM0051 & VM0047 compliant"
        />
      </div>

      {/* Registry Standards Cross-Reference Cards */}
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <Card className="p-4 bg-surface-2/30">
          <div className="flex items-center justify-between">
            <span className="font-bold text-sm">Verra VCS Program</span>
            <Badge tone="brand">VM0051 / VM0047</Badge>
          </div>
          <p className="text-xs text-muted mt-1.5">
            Full methodology alignment with dynamic performance benchmarks. Avoided methane qualifies under CORSIA aviation offsets.
          </p>
        </Card>

        <Card className="p-4 bg-surface-2/30">
          <div className="flex items-center justify-between">
            <span className="font-bold text-sm">Gold Standard for Global Goals</span>
            <Badge tone="neutral">Co-Benefits</Badge>
          </div>
          <p className="text-xs text-muted mt-1.5">
            Fair-trade farmer benefit-sharing: 60% gross proceeds transferred with audited bank references.
          </p>
        </Card>

        <Card className="p-4 bg-surface-2/30">
          <div className="flex items-center justify-between">
            <span className="font-bold text-sm">Article 6 & Corresponding Adjustments</span>
            <Badge tone="info">Article 6.2 ITMO</Badge>
          </div>
          <p className="text-xs text-muted mt-1.5">
            Host country letters of authorization (LoA) tracked to avoid double-claiming against host Nationally Determined Contributions (NDCs).
          </p>
        </Card>
      </div>

      {/* Serialized Vintages Table */}
      <div className="mt-6">
        <Card>
          <CardHeader
            title="Serialized Credit Vintages"
            description="Verified issuances and active batches."
          />
          {vintages.length === 0 ? (
            <EmptyState
              title="No vintages created yet"
              body="Vintages are generated after a season's satellite monitoring and field measurements are closed."
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Vintage ID / Reference</Th>
                  <Th>Project Name</Th>
                  <Th>Year</Th>
                  <Th>Volume (tCO₂e)</Th>
                  <Th>Status</Th>
                  <Th>Registry Ref</Th>
                  <Th>Evidence Pack</Th>
                  <Th>Actions</Th>
                </tr>
              </thead>
              <tbody>
                {vintages.map((v) => {
                  const proj = projects.find((p) => p.id === v.project_id);
                  return (
                    <tr key={v.id}>
                      <Td className="font-semibold text-xs sm:text-sm">
                        <Link href={`/app/credits/${v.id}`} className="hover:text-brand transition">
                          {v.serial_start !== null ? `${v.id.slice(0, 8)}-${v.year}` : v.id.slice(0, 12)}
                        </Link>
                      </Td>
                      <Td className="text-xs font-medium">{proj?.name ?? "—"}</Td>
                      <Td className="text-xs tabular">{v.year}</Td>
                      <Td className="text-xs tabular font-bold text-brand">{fmt.int(v.issuable)} t</Td>
                      <Td>
                        <Badge tone={VINTAGE_TONE[v.status]}>{VINTAGE_LABEL[v.status]}</Badge>
                      </Td>
                      <Td className="text-xs font-mono text-muted">{v.registry_ref || "Pending registry allocation"}</Td>
                      <Td>
                        <Link
                          href={`/app/credits/${v.id}/pack`}
                          className="inline-flex items-center gap-1 text-xs text-brand hover:underline font-medium"
                        >
                          <FolderLock className="h-3 w-3" /> SHA-256 Pack
                        </Link>
                      </Td>
                      <Td>
                        <Link
                          href={`/app/credits/${v.id}`}
                          className="text-xs font-semibold text-brand hover:underline"
                        >
                          Details →
                        </Link>
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
    </>
  );
}
