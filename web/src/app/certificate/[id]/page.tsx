import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PrintButton } from "@/components/public/print-button";
import { PublicShell } from "@/components/public/public-shell";
import { VintageFacts } from "@/components/public/vintage-facts";
import { Card } from "@/components/ui";
import { PURPOSE_LABEL } from "@/lib/claims";
import { retirementCertificate } from "@/lib/data";
import { fmt } from "@/lib/format";

export const metadata: Metadata = { title: "Retirement certificate" };

export default async function CertificatePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const c = await retirementCertificate(id);
  if (!c.found) notFound();
  const v = c.vintage;
  return (
    <PublicShell>
      <Card className="mt-8 p-8 print:border-0 print:p-0">
        <div className="text-xs font-medium uppercase tracking-widest text-brand">Retirement certificate</div>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          {c.quantity} tonne{c.quantity === 1 ? "" : "s"} of CO₂e retired for {c.beneficiary}
        </h1>
        <p className="mt-1 text-sm text-muted">
          {PURPOSE_LABEL[c.purpose]} · {fmt.datetime(c.retired_at)}
        </p>
        <blockquote className="mt-5 border-l-4 border-brand pl-4 text-sm">{c.claim}</blockquote>
        <div className="mt-6 rounded-lg bg-surface-2 p-4 font-mono text-sm">
          {v.org_code}-{v.vintage_year}-{c.serial_start} to {v.org_code}-{v.vintage_year}-{c.serial_end}
        </div>
        <div className="mt-6">
          <VintageFacts v={v} />
        </div>
        <p className="mt-6 text-xs text-muted">
          Certificate {c.id}. Any serial in this range can be checked at /verify. These credits cannot be retired again.
        </p>
        <div className="mt-4 print:hidden">
          <PrintButton />
        </div>
      </Card>
    </PublicShell>
  );
}
