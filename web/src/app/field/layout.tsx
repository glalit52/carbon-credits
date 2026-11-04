import type { Metadata, Viewport } from "next";
import Link from "next/link";

import { LanguagePicker, ServiceWorker } from "@/components/field/shell";
import { Logo } from "@/components/logo";
import { Badge } from "@/components/ui";
import { getOrgContext } from "@/lib/data";
import { fieldLanguage } from "@/lib/field-lang";
import { translator } from "@/lib/i18n";

export const metadata: Metadata = { title: "Field", manifest: "/field.webmanifest" };
export const viewport: Viewport = { themeColor: "#1f7a4d", width: "device-width", initialScale: 1 };

export default async function FieldLayout({ children }: { children: React.ReactNode }) {
  const [ctx, lang] = await Promise.all([getOrgContext(), fieldLanguage()]);
  const t = translator(lang);
  return (
    <div className="mx-auto flex min-h-dvh max-w-lg flex-col bg-bg">
      <header className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-border bg-surface px-4 py-3">
        <Logo href="/field" />
        <div className="flex items-center gap-2">
          <LanguagePicker current={lang} />
          <Link href="/app" className="text-xs text-muted underline">
            {t("field.back_office")}
          </Link>
        </div>
      </header>
      {ctx.demo && (
        <div className="border-b border-border bg-accent-soft px-4 py-2 text-xs">
          <Badge tone="accent">Demo</Badge> Enrolments are kept on this phone; the demo cannot save them.
        </div>
      )}
      <main className="flex-1 px-4 py-5">{children}</main>
      <ServiceWorker />
    </div>
  );
}
