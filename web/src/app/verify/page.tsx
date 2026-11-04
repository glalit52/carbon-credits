import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PublicShell } from "@/components/public/public-shell";
import { Button, Card, Input } from "@/components/ui";

export const metadata: Metadata = { title: "Verify a credit" };

async function lookup(form: FormData) {
  "use server";
  const code = String(form.get("code") ?? "").trim();
  if (code) redirect(`/verify/${encodeURIComponent(code)}`);
}

export default function VerifyPage() {
  return (
    <PublicShell>
      <h1 className="mt-8 text-2xl font-semibold tracking-tight">Verify a carbon credit</h1>
      <p className="mt-2 text-muted">
        Enter the credit code from a certificate or invoice to see who issued it, under which methodology, and whether
        it has already been retired — and for whom.
      </p>
      <Card className="mt-6 p-5">
        <form action={lookup} className="flex flex-col gap-3 sm:flex-row">
          <Input name="code" placeholder="e.g. 7C3E9A51-2025-6" aria-label="Credit code" required className="font-mono" />
          <Button type="submit">Look up</Button>
        </form>
        <p className="mt-3 text-xs text-muted">
          A code is the issuer&apos;s eight-character prefix, the vintage year and the serial number.
        </p>
      </Card>
    </PublicShell>
  );
}
