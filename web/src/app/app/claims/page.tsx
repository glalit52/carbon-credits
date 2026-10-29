import { ExternalLink } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { ActionForm } from "@/components/action-form";
import { Badge, Card, CardHeader, EmptyState, Field, Input, PageHeader, Select, Stat, Table, Td, Th } from "@/components/ui";
import { addAdjustment, addAuthorisation, retireCredits } from "@/lib/actions/claims";
import { buyerLanguage, PURPOSE_LABEL } from "@/lib/claims";
import {
  creditCode,
  getOrgContext,
  listAdjustments,
  listAuthorisations,
  listProjects,
  listRetirements,
  listVintages,
  vintageClaims,
} from "@/lib/data";
import { fmt } from "@/lib/format";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Claims & retirement" };

const USE_LABEL = {
  other_party_ndc: "Another country's NDC",
  corsia: "CORSIA",
  other_international_mitigation_purposes: "Other international purposes",
} as const;

export default async function ClaimsPage() {
  const ctx = await getOrgContext();
  const [vintages, projects, retirements, claims, authorisations, adjustments] = await Promise.all([
    listVintages(ctx.org.id),
    listProjects(ctx.org.id),
    listRetirements(ctx.org.id),
    vintageClaims(ctx.org.id),
    listAuthorisations(ctx.org.id),
    listAdjustments(ctx.org.id),
  ]);
  const admin = can.administer(ctx.role);
  const project = new Map(projects.map((p) => [p.id, p]));
  const issued = vintages.filter((v) => v.status === "issued");
  const retiredIn = (id: string) => retirements.filter((r) => r.vintage_id === id).reduce((s, r) => s + r.quantity, 0);
  const totalIssued = issued.reduce((s, v) => s + v.issuable, 0);
  const totalRetired = retirements.reduce((s, r) => s + r.quantity, 0);
  const offsetRemaining = issued.reduce((s, v) => s + (claims.get(v.id)?.offset_remaining ?? 0), 0);
  const vintageById = new Map(vintages.map((v) => [v.id, v]));
  const authRef = new Map(authorisations.map((a) => [a.id, a.reference]));

  return (
    <>
      <PageHeader
        title="Claims & retirement"
        description="What a buyer of each credit may truthfully say, and the record of credits being used. A host country's authorisation letter is a promise; only a corresponding adjustment lets a credit count against a buyer's own target."
        actions={
          <Link href="/verify" className="flex items-center gap-1 text-sm font-medium text-brand" target="_blank">
            Public verification page <ExternalLink className="h-4 w-4" />
          </Link>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Issued" value={fmt.int(totalIssued)} hint="whole credits" />
        <Stat label="Retired" value={fmt.int(totalRetired)} />
        <Stat label="Available" value={fmt.int(totalIssued - totalRetired)} tone="brand" />
        <Stat label="Available as offsets" value={fmt.int(offsetRemaining)} hint="adjustment applied" />
      </div>

      <div className="flex flex-col gap-6">
        {issued.length === 0 && (
          <Card>
            <EmptyState title="No issued credits yet" body="Credits appear here once a vintage is approved and issued." />
          </Card>
        )}
        {issued.map((v) => {
          const p = project.get(v.project_id);
          const c = claims.get(v.id);
          const retired = retiredIn(v.id);
          const left = v.issuable - retired;
          return (
            <Card key={v.id}>
              <CardHeader
                title={
                  <span>
                    {p?.name} · {v.year}{" "}
                    <Badge tone={c && c.offsettable_credits > 0 ? "brand" : "neutral"} className="ml-1">
                      {c && c.offsettable_credits > 0 ? "Adjusted ITMO" : c?.basis === "authorised_itmo" ? "Authorised, not adjusted" : "Unadjusted voluntary"}
                    </Badge>
                    {c?.corsia_eligible && (
                      <Badge tone="info" className="ml-1">
                        CORSIA eligible
                      </Badge>
                    )}
                  </span>
                }
                description={`Serials ${creditCode(v.org_id, v.year, v.serial_start ?? 0)} to ${v.serial_end} · ${v.issuable} issued · ${retired} retired · ${left} left`}
              />
              <div className="grid gap-6 p-5 lg:grid-cols-2">
                <div className="text-sm">
                  <h3 className="mb-1 font-semibold">What a buyer may say</h3>
                  <p className="text-muted">{buyerLanguage(c, p?.country ?? null)}</p>
                  {c?.authorisation && (
                    <p className="mt-2 text-xs text-muted">
                      Authorisation {c.authorisation.reference} by {c.authorisation.authority} for{" "}
                      {USE_LABEL[c.authorisation.authorised_use]}; {fmt.num(c.adjusted_t, 2)} t adjusted for {v.year}.
                    </p>
                  )}
                  {c?.reasons?.length ? (
                    <ul className="mt-2 list-disc pl-4 text-xs text-muted">
                      {c.reasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
                {admin && left > 0 ? (
                  <ActionForm action={retireCredits} submit="Retire credits" hidden={{ vintage_id: v.id }}>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <Field label="Credits">
                        <Input name="credits" type="number" min={1} max={left} defaultValue={1} required />
                      </Field>
                      <Field label="For" className="sm:col-span-2">
                        <Input name="beneficiary" placeholder="Company or person" required />
                      </Field>
                    </div>
                    <Field
                      label="Purpose"
                      hint={`${c?.offset_remaining ?? 0} of these may be retired as offsets; the rest only as contributions.`}
                    >
                      <Select name="purpose" defaultValue="contribution">
                        <option value="contribution">{PURPOSE_LABEL.contribution} — financed, not counted against own target</option>
                        <option value="offset" disabled={!c?.offset_remaining}>
                          {PURPOSE_LABEL.offset}
                        </option>
                        <option value="corsia" disabled={!c?.corsia_eligible || !c.offset_remaining}>
                          {PURPOSE_LABEL.corsia}
                        </option>
                      </Select>
                    </Field>
                  </ActionForm>
                ) : (
                  <p className="text-sm text-muted">{left > 0 ? "Owners and admins retire credits." : "Every credit in this vintage is retired."}</p>
                )}
              </div>
            </Card>
          );
        })}

        <Card>
          <CardHeader title="Retirements" description="Each one has a public certificate anyone can check." />
          {retirements.length ? (
            <Table>
              <thead>
                <tr>
                  <Th>Retired</Th>
                  <Th>For</Th>
                  <Th>Purpose</Th>
                  <Th>Credits</Th>
                  <Th>Serials</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {retirements.map((r) => {
                  const v = vintageById.get(r.vintage_id);
                  return (
                    <tr key={r.id}>
                      <Td className="whitespace-nowrap text-xs text-muted">{fmt.date(r.retired_at)}</Td>
                      <Td className="font-medium">{r.beneficiary}</Td>
                      <Td>
                        <Badge tone={r.purpose === "contribution" ? "neutral" : "brand"}>{PURPOSE_LABEL[r.purpose]}</Badge>
                      </Td>
                      <Td className="tabular">{r.quantity}</Td>
                      <Td className="tabular text-xs">
                        {v ? `${creditCode(v.org_id, v.year, r.serial_start)} – ${r.serial_end}` : `${r.serial_start}–${r.serial_end}`}
                      </Td>
                      <Td className="text-right">
                        <Link href={`/certificate/${r.id}`} target="_blank" className="text-xs font-medium text-brand">
                          Certificate
                        </Link>
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          ) : (
            <EmptyState title="Nothing retired yet" />
          )}
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Article 6 authorisations" description="Letters from the host country authorising transfer." />
            {authorisations.length ? (
              <ul className="divide-y divide-border text-sm">
                {authorisations.map((a) => (
                  <li key={a.id} className="px-5 py-3">
                    <div className="font-medium">
                      {a.reference} · {project.get(a.project_id)?.name}
                    </div>
                    <div className="text-xs text-muted">
                      {a.authority}, {fmt.date(a.issued_on)} · {USE_LABEL[a.authorised_use]} · vintages {a.first_vintage}–
                      {a.last_vintage} · {fmt.t(a.authorised_volume_t)} ·{" "}
                      {a.adjustment_committed ? "commits to a corresponding adjustment" : "no adjustment commitment"}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="None recorded" body="Without one, credits can only be retired as contributions." />
            )}
            {admin && (
              <details className="border-t border-border p-5">
                <summary className="cursor-pointer text-sm font-medium text-brand">Record an authorisation</summary>
                <ActionForm action={addAuthorisation} submit="Save authorisation" variant="secondary" className="mt-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Project" className="sm:col-span-2">
                      <Select name="project_id" required>
                        {projects.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Issuing authority">
                      <Input name="authority" placeholder="MoEFCC, Government of India" required />
                    </Field>
                    <Field label="Letter reference">
                      <Input name="reference" required />
                    </Field>
                    <Field label="Issued on">
                      <Input name="issued_on" type="date" required />
                    </Field>
                    <Field label="Authorised for">
                      <Select name="authorised_use" defaultValue="other_party_ndc">
                        {Object.entries(USE_LABEL).map(([k, l]) => (
                          <option key={k} value={k}>
                            {l}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Volume (t)">
                      <Input name="authorised_volume_t" type="number" step="0.01" min={0} required />
                    </Field>
                    <Field label="Commits to a corresponding adjustment?">
                      <Select name="adjustment_committed" defaultValue="yes">
                        <option value="yes">Yes</option>
                        <option value="no">No</option>
                      </Select>
                    </Field>
                    <Field label="First vintage">
                      <Input name="first_vintage" type="number" required />
                    </Field>
                    <Field label="Last vintage">
                      <Input name="last_vintage" type="number" required />
                    </Field>
                    <Field label="Valid until (optional)">
                      <Input name="valid_until" type="date" />
                    </Field>
                  </div>
                </ActionForm>
              </details>
            )}
          </Card>

          <Card>
            <CardHeader title="Corresponding adjustments" description="What the host country has actually applied and reported." />
            {adjustments.length ? (
              <ul className="divide-y divide-border text-sm">
                {adjustments.map((a) => (
                  <li key={a.id} className="px-5 py-3">
                    <div className="font-medium">
                      {fmt.t(a.volume_t, 2)} for {a.vintage_year}
                    </div>
                    <div className="text-xs text-muted">
                      under {authRef.get(a.authorisation_id)} · reported {fmt.date(a.reported_on)} in {a.reference}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="None reported" body="Until one is, no credit may be sold as an offset." />
            )}
            {admin && authorisations.length > 0 && (
              <details className="border-t border-border p-5">
                <summary className="cursor-pointer text-sm font-medium text-brand">Record an adjustment</summary>
                <ActionForm action={addAdjustment} submit="Save adjustment" variant="secondary" className="mt-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Under authorisation" className="sm:col-span-2">
                      <Select name="authorisation_id" required>
                        {authorisations.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.reference}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Vintage year">
                      <Input name="vintage_year" type="number" required />
                    </Field>
                    <Field label="Volume (t)">
                      <Input name="volume_t" type="number" step="0.01" min={0} required />
                    </Field>
                    <Field label="Reported on">
                      <Input name="reported_on" type="date" required />
                    </Field>
                    <Field label="Report reference" hint="e.g. the Biennial Transparency Report table">
                      <Input name="reference" required />
                    </Field>
                  </div>
                </ActionForm>
              </details>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
