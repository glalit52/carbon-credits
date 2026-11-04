import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { StatementView } from "@/components/statement-view";
import { getFarmer, getOrgContext, memberStatement } from "@/lib/data";
import { isLanguage, LANGUAGES } from "@/lib/i18n";

export const metadata: Metadata = { title: "Statement" };

export default async function FarmerStatementPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ lang?: string }>;
}) {
  const [{ id }, { lang }] = await Promise.all([params, searchParams]);
  const ctx = await getOrgContext();
  const farmer = await getFarmer(ctx.org.id, id);
  if (!farmer) notFound();
  const language = isLanguage(lang) ? lang : farmer.language;
  const s = await memberStatement(ctx.org.id, id, language);
  if (!s.found) notFound();
  return (
    <div className="mx-auto max-w-2xl">
      <nav className="mb-4 flex flex-wrap items-center gap-2 text-sm print:hidden">
        <Link href={`/app/farmers/${id}`} className="text-muted hover:text-text">
          ← {farmer.name}
        </Link>
        <span className="ml-auto flex gap-1">
          {LANGUAGES.map((l) => (
            <Link
              key={l.code}
              href={`?lang=${l.code}`}
              className={`rounded-md px-2 py-1 ${l.code === language ? "bg-brand-soft font-medium text-brand-strong" : "text-muted hover:bg-surface-2"}`}
            >
              {l.native}
            </Link>
          ))}
        </span>
      </nav>
      <StatementView s={s} />
    </div>
  );
}
