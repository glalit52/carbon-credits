import {
  Download,
  FileSpreadsheet,
  FolderLock,
} from "lucide-react";
import type { Metadata } from "next";

import { Badge, ButtonLink, Card, CardHeader, PageHeader, Table, Td, Th } from "@/components/ui";
import { getOrgContext, listVintages } from "@/lib/data";
import { fmt } from "@/lib/format";

export const metadata: Metadata = { title: "Audit & MRV Reports" };

export default async function ReportsPage() {
  const ctx = await getOrgContext();
  const vintages = await listVintages(ctx.org.id);

  const issuedVintages = vintages.filter((v) => v.status === "issued");

  const REPORT_TYPES = [
    {
      id: "dmrv-monitoring",
      title: "Quarterly dMRV Remote Sensing & Telemetry Report",
      standard: "Verra VM0051 / VM0047",
      desc: "Complete pass-by-pass Copernicus Sentinel-1 SAR radar backscatter log, water layer calls, and weather normals across all enrolled parcels.",
      frequency: "Quarterly / End-of-Season",
      actionHref: "/app/export/farms.csv",
      actionLabel: "Export Telemetry CSV",
    },
    {
      id: "pdd-summary",
      title: "VCS Project Description Document (PDD) Summary",
      standard: "VCS Standard v4.4",
      desc: "Formal project design document summary covering baseline methanogenesis, dynamic benchmarks, additionality, and non-permanence risk analysis.",
      frequency: "Annual / Verification",
      actionHref: "/app/export/farms.geojson",
      actionLabel: "Export Boundaries GeoJSON",
    },
    {
      id: "farmer-settlement",
      title: "Farmer Fair-Share Benefit Settlement Ledger",
      standard: "Gold Standard Fair Trade",
      desc: "Audited disbursement schedule detailing 60% gross proceeds distribution per farmer with banking and mobile-money transaction references.",
      frequency: "Per Vintage Payout",
      actionHref: "/app/payments",
      actionLabel: "View Settlement Slips",
    },
    {
      id: "registry-reconciliation",
      title: "Registry Reconciliation & Serial Tracking Certificate",
      standard: "VCS / CORSIA / GS",
      desc: "Complete serial number reconciliation against external registry exports (Verra, Gold Standard, Puro, or Isometric).",
      frequency: "Post-Issuance",
      actionHref: "/app/credits/registry",
      actionLabel: "Reconciliation Tool",
    },
  ];

  return (
    <>
      <PageHeader
        title="Audit & MRV Reports Generator"
        crumbs={[{ href: "/app", label: "App" }, { href: "/app/reports", label: "Reports" }]}
        description="Formal audit documentation, quarterly remote-sensing telemetry packs, and farmer benefit-sharing settlement records."
      />

      {/* Available Formal Reports */}
      <div className="grid gap-4 sm:grid-cols-2">
        {REPORT_TYPES.map((rep) => (
          <Card key={rep.id} className="p-5 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted uppercase tracking-wider">{rep.frequency}</span>
                <Badge tone="brand">{rep.standard}</Badge>
              </div>
              <h3 className="mt-2 text-base font-bold text-text">{rep.title}</h3>
              <p className="mt-1.5 text-xs text-muted leading-relaxed">{rep.desc}</p>
            </div>

            <div className="mt-5 pt-3 border-t border-border flex items-center justify-between">
              <span className="text-[11px] text-muted">Audited & SHA-256 Validated</span>
              <ButtonLink href={rep.actionHref} variant="secondary" className="text-xs py-1.5">
                <FileSpreadsheet className="h-3.5 w-3.5" /> {rep.actionLabel}
              </ButtonLink>
            </div>
          </Card>
        ))}
      </div>

      {/* Issued Vintages Evidence Packs */}
      <div className="mt-6">
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <FolderLock className="h-4 w-4 text-brand" />
                <span>Audited Vintage Evidence Packs</span>
              </div>
            }
            description="Complete zip packages containing plot registers, geo-boundaries, radar passes, review audit trails, and SHA-256 manifests."
          />
          {issuedVintages.length === 0 ? (
            <div className="p-8 text-center text-xs text-muted">
              No issued vintages currently available. Once a vintage is approved, its immutable evidence pack is generated here.
            </div>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Vintage Identifier</Th>
                  <Th>Vintage Year</Th>
                  <Th>Issued Volume</Th>
                  <Th>Evidence Pack Contents</Th>
                  <Th>Action</Th>
                </tr>
              </thead>
              <tbody>
                {issuedVintages.map((v) => (
                  <tr key={v.id}>
                    <Td className="font-semibold text-xs sm:text-sm">
                      {v.serial_start !== null ? `${v.id.slice(0, 8)}-${v.year}` : v.id.slice(0, 10)}
                    </Td>
                    <Td className="text-xs tabular">{v.year}</Td>
                    <Td className="text-xs tabular font-bold text-brand">{fmt.int(v.issuable)} tCO₂e</Td>
                    <Td className="text-xs text-muted">Boundaries, Radar Passes, Soil Samples, Review Trail, SHA-256 Manifest</Td>
                    <Td>
                      <ButtonLink href={`/app/credits/${v.id}/pack`} variant="secondary" className="text-xs py-1">
                        <Download className="h-3 w-3" /> Download Pack (.zip)
                      </ButtonLink>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
    </>
  );
}
