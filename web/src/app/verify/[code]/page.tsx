import { CheckCircle2, CircleSlash, SearchX } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { PublicShell } from "@/components/public/public-shell";
import { VintageFacts } from "@/components/public/vintage-facts";
import { Card } from "@/components/ui";
import { PURPOSE_LABEL } from "@/lib/claims";
import { verifyCredit } from "@/lib/data";
import { fmt } from "@/lib/format";

export const metadata: Metadata = { title: "Credit lookup" };

export default async function CreditPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const result = await verifyCredit(decodeURIComponent(code));

  if (!result.found) {
    return (
      <PublicShell>
        <Card className="mt-8 p-8 text-center">
          <SearchX className="mx-auto h-8 w-8 text-muted" />
          <h1 className="mt-3 text-lg font-semibold">No issued credit has the code {decodeURIComponent(code)}</h1>
          <p className="mt-1 text-sm text-muted">{result.reason ?? "Check the code and try again."}</p>
          <Link href="/verify" className="mt-4 inline-block text-sm font-medium text-brand">
            Try another code
          </Link>
        </Card>
      </PublicShell>
    );
  }

  const r = result.retirement;
  return (
    <PublicShell>
      <Card className="mt-8 overflow-hidden">
        <div className={`flex items-center gap-3 px-6 py-5 ${r ? "bg-surface-2" : "bg-brand-soft"}`}>
          {r ? <CircleSlash className="h-7 w-7 text-muted" /> : <CheckCircle2 className="h-7 w-7 text-brand" />}
          <div>
            <div className="font-mono text-sm">{result.code}</div>
            <h1 className="text-lg font-semibold">
              {r ? `Retired for ${r.beneficiary}` : "Issued and not yet retired"}
            </h1>
          </div>
        </div>
        {r && (
          <div className="border-b border-border px-6 py-4 text-sm">
            <div>
              {PURPOSE_LABEL[r.purpose]} · {fmt.date(r.retired_at)} · part of a retirement of {r.quantity} credit
              {r.quantity === 1 ? "" : "s"} (serials {r.serial_start}–{r.serial_end})
            </div>
            <p className="mt-2 text-muted">“{r.claim}”</p>
            <Link href={`/certificate/${r.id}`} className="mt-2 inline-block font-medium text-brand">
              View the retirement certificate
            </Link>
          </div>
        )}
        <div className="px-6 py-5">
          <VintageFacts v={result.vintage} />
        </div>
      </Card>
    </PublicShell>
  );
}
