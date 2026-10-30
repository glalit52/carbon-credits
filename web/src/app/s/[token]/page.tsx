import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Logo } from "@/components/logo";
import { StatementView } from "@/components/statement-view";
import { farmerStatement } from "@/lib/data";

// A farmer's own statement, opened from a link a field agent shared. The
// token is the only key, so the page is never indexed or cached.
export const metadata: Metadata = { title: "Statement", robots: { index: false, follow: false } };

export default async function SharedStatement({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const s = await farmerStatement(token);
  if (!s.found) notFound();
  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <div className="mb-6 print:hidden">
        <Logo />
      </div>
      <StatementView s={s} />
    </div>
  );
}
