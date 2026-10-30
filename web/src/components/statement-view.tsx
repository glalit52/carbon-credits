import type { FarmerStatement } from "@/lib/database.types";
import { LOCALE, translator } from "@/lib/i18n";

import { PrintLabel } from "./public/print-button";
import { Card, Table, Td, Th } from "./ui";

type Found = Extract<FarmerStatement, { found: true }>;

/**
 * A farmer's statement, in their language. The same page whether a field
 * agent opens it in the back office or the farmer opens it from a link.
 */
export function StatementView({ s }: { s: Found }) {
  const t = translator(s.language);
  const locale = LOCALE[s.language];
  const num = (n: number, d = 2) => new Intl.NumberFormat(locale, { maximumFractionDigits: d }).format(n);
  const money = (n: number, c: string) =>
    new Intl.NumberFormat(locale, { style: "currency", currency: c, maximumFractionDigits: 2 }).format(n);
  const date = (d: string | null) =>
    d ? new Date(d.length === 10 ? `${d}T00:00:00Z` : d).toLocaleDateString(locale, { dateStyle: "medium", timeZone: "UTC" }) : "—";

  const todo = [
    !s.farmer.consent && t("st.todo_consent"),
    !s.farmer.carbon_rights && t("st.todo_rights"),
    ...s.farms.filter((f) => !f.tenure_document).map((f) => `${t("st.todo_tenure")} ${f.name}`),
  ].filter(Boolean) as string[];
  const paid = s.payments.filter((p) => p.status === "paid");

  return (
    <article lang={s.language} className="flex flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-widest text-brand">{t("st.title")}</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">{s.farmer.name}</h1>
          <p className="text-sm text-muted">
            {[s.farmer.village, s.farmer.district, s.farmer.external_ref].filter(Boolean).join(" · ")}
          </p>
          <p className="mt-1 text-sm">
            {t("st.from")}: <span className="font-medium">{s.organisation}</span> · {date(s.generated_at)}
          </p>
        </div>
        <PrintLabel label={t("st.print")} />
      </header>

      <div className="grid grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="text-xs text-muted">{t("st.farms")}</div>
          <div className="mt-1 text-xl font-semibold tabular">
            {s.farms.length} · {num(s.farms.reduce((a, f) => a + Number(f.area_ha), 0))} ha
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-muted">{t("st.payments")}</div>
          <div className="mt-1 text-xl font-semibold tabular">
            {paid.length
              ? [...new Set(paid.map((p) => p.currency))]
                  .map((c) => money(paid.filter((p) => p.currency === c).reduce((a, p) => a + Number(p.amount), 0), c))
                  .join(" + ")
              : "—"}
          </div>
        </Card>
      </div>

      <Card>
        <h2 className="border-b border-border px-4 py-3 text-sm font-semibold">{t("st.farms")}</h2>
        <Table className="[&_table]:min-w-0">
          <thead>
            <tr>
              <Th />
              <Th className="text-right">{t("st.area")}</Th>
              <Th className="text-right">{t("st.estimate")}</Th>
            </tr>
          </thead>
          <tbody>
            {s.farms.map((f) => (
              <tr key={f.name}>
                <Td>
                  <div className="font-medium">{f.name}</div>
                  <div className="text-xs text-muted">{f.project}</div>
                </Td>
                <Td className="tabular text-right">{num(Number(f.area_ha))} ha</Td>
                <Td className="tabular text-right">
                  {f.latest_net_t == null ? "—" : `${num(Number(f.latest_net_t))} ${t("st.tonnes")}`}
                  {f.latest_year != null && <div className="text-xs text-muted">{f.latest_year}</div>}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      <Card>
        <h2 className="border-b border-border px-4 py-3 text-sm font-semibold">{t("st.payments")}</h2>
        {s.payments.length ? (
          <Table className="[&_table]:min-w-0">
            <thead>
              <tr>
                <Th>{t("st.year")}</Th>
                <Th className="text-right">{t("st.credits")}</Th>
                <Th className="text-right">{t("st.amount")}</Th>
                <Th>{t("st.status")}</Th>
              </tr>
            </thead>
            <tbody>
              {s.payments.map((p) => (
                <tr key={`${p.vintage_year}-${p.project}`}>
                  <Td>
                    {p.vintage_year}
                    <div className="text-xs text-muted">{p.project}</div>
                  </Td>
                  <Td className="tabular text-right">{num(Number(p.credits), 3)}</Td>
                  <Td className="tabular text-right">{money(Number(p.amount), p.currency)}</Td>
                  <Td>
                    {t(`pay.${p.status}`)}
                    {p.paid_on && (
                      <div className="text-xs text-muted">
                        {t("st.paid_on")} {date(p.paid_on)}
                        {p.reference_tail && ` · ${t("st.ref")} …${p.reference_tail}`}
                      </div>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <p className="p-4 text-sm text-muted">{t("st.no_payments")}</p>
        )}
      </Card>

      <Card className="p-4">
        <h2 className="text-sm font-semibold">{t("st.todo")}</h2>
        {todo.length ? (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {todo.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-brand">{t("st.all_done")}</p>
        )}
      </Card>

      <p className="text-xs text-muted">
        {t("st.note")}
        {s.expires_at && ` ${t("st.expires")} ${date(s.expires_at)}.`}
      </p>
    </article>
  );
}
