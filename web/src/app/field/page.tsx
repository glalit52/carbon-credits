import { Plus } from "lucide-react";
import Link from "next/link";

import { QueueList } from "@/components/field/queue-list";
import { Card } from "@/components/ui";
import { getOrgContext, listFarms } from "@/lib/data";
import { fieldLanguage } from "@/lib/field-lang";
import { translator } from "@/lib/i18n";
import { fmt } from "@/lib/format";

export default async function FieldHome() {
  const [ctx, lang] = await Promise.all([getOrgContext(), fieldLanguage()]);
  const t = translator(lang);
  const mine = (await listFarms(ctx.org.id))
    .filter((f) => f.created_by === ctx.user.id)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 10);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("field.title")}</h1>
      <Link
        href="/field/enrol"
        className="flex items-center justify-center gap-2 rounded-xl bg-brand px-4 py-5 text-lg font-medium text-white shadow-sm active:bg-brand-strong"
      >
        <Plus className="h-6 w-6" /> {t("field.enrol")}
      </Link>
      <QueueList lang={lang} />
      <section>
        <h2 className="mb-2 text-sm font-semibold text-muted">{t("field.recent")}</h2>
        {mine.length ? (
          <Card>
            <ul className="divide-y divide-border">
              {mine.map((f) => (
                <li key={f.id} className="flex items-center justify-between px-4 py-3 text-sm">
                  <span className="font-medium">{f.name}</span>
                  <span className="text-muted">{fmt.ha(f.area_ha)}</span>
                </li>
              ))}
            </ul>
          </Card>
        ) : (
          <p className="text-sm text-muted">—</p>
        )}
      </section>
    </div>
  );
}
