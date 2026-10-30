import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/action-form";
import { CopyButton } from "@/components/copy-button";
import { FarmMap } from "@/components/map/farm-map";
import {
  Badge,
  ButtonLink,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
} from "@/components/ui";
import {
  createStatementLink,
  revokeStatementLink,
} from "@/lib/actions/statements";
import {
  getFarmer,
  getOrgContext,
  listFarms,
  listPayments,
  listStatementLinks,
  listVintages,
} from "@/lib/data";
import { siteUrl } from "@/lib/env";
import { LANGUAGES, translator } from "@/lib/i18n";
import { fmt, PAYMENT_TONE } from "@/lib/format";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Farmer" };

export default async function FarmerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const ctx = await getOrgContext();
  const farmer = await getFarmer(ctx.org.id, id);
  if (!farmer) notFound();
  const [farms, payments, vintages, links] = await Promise.all([
    listFarms(ctx.org.id, { farmerId: id }),
    listPayments(ctx.org.id),
    listVintages(ctx.org.id),
    listStatementLinks(ctx.org.id, id),
  ]);
  const now = new Date().toISOString();
  const live = links.filter((l) => !l.revoked_at && l.expires_at > now);
  const phone = farmer.phone?.replace(/\D/g, "") ?? "";
  const own = payments.filter((p) => p.farmer_id === id);
  const vintageYear = new Map(vintages.map((v) => [v.id, v.year]));

  return (
    <>
      <PageHeader
        crumbs={[{ href: "/app/farmers", label: "Farmers" }]}
        title={farmer.name}
        description={[
          farmer.external_ref,
          farmer.village,
          farmer.district,
          farmer.country,
        ]
          .filter(Boolean)
          .join(" · ")}
        actions={
          can.enrol(ctx.role) && (
            <ButtonLink
              href={`/app/farmers/${farmer.id}/edit`}
              variant="secondary"
            >
              Edit
            </ButtonLink>
          )
        }
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          {farms.length > 0 && (
            <FarmMap
              farms={farms.map((f) => ({
                id: f.id,
                name: f.name,
                boundary: f.boundary,
                status: f.status,
                area_ha: Number(f.area_ha),
              }))}
              className="h-72"
            />
          )}
          <Card>
            <CardHeader title="Farms" />
            {farms.length ? (
              <Table>
                <thead>
                  <tr>
                    <Th>Farm</Th>
                    <Th className="text-right">Area</Th>
                    <Th>Status</Th>
                  </tr>
                </thead>
                <tbody>
                  {farms.map((f) => (
                    <tr key={f.id}>
                      <Td>
                        <Link
                          href={`/app/farms/${f.id}`}
                          className="font-medium hover:text-brand"
                        >
                          {f.name}
                        </Link>
                      </Td>
                      <Td className="tabular text-right">
                        {fmt.ha(f.area_ha)}
                      </Td>
                      <Td>
                        <Badge
                          tone={f.status === "enrolled" ? "brand" : "accent"}
                        >
                          {f.status}
                        </Badge>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="No farms linked" />
            )}
          </Card>
          <Card>
            <CardHeader
              title="Payments"
              description="This farmer's share of issued credits."
            />
            {own.length ? (
              <Table>
                <thead>
                  <tr>
                    <Th>Vintage</Th>
                    <Th className="text-right">Credits</Th>
                    <Th className="text-right">Amount</Th>
                    <Th>Status</Th>
                    <Th>Paid</Th>
                  </tr>
                </thead>
                <tbody>
                  {own.map((p) => (
                    <tr key={p.id}>
                      <Td>{vintageYear.get(p.vintage_id) ?? "—"}</Td>
                      <Td className="tabular text-right">
                        {fmt.num(p.credits, 3)}
                      </Td>
                      <Td className="tabular text-right">
                        {fmt.money(p.amount, p.currency)}
                      </Td>
                      <Td>
                        <Badge tone={PAYMENT_TONE[p.status]}>{p.status}</Badge>
                      </Td>
                      <Td className="text-xs text-muted">
                        {fmt.date(p.paid_on)} {p.reference}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="Nothing paid yet" />
            )}
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader
              title="Statement"
              description="What this farmer has enrolled, earned and still needs to provide, in their language."
              action={
                <ButtonLink
                  href={`/app/farmers/${farmer.id}/statement`}
                  variant="secondary"
                >
                  Open
                </ButtonLink>
              }
            />
            <div className="flex flex-col gap-4 p-5">
              {live.map((l) => {
                const url = `${siteUrl()}/s/${l.token}`;
                const text = `${translator(l.language)("share.message", { org: ctx.org.name })} ${url}`;
                return (
                  <div
                    key={l.id}
                    className="rounded-lg border border-border p-3 text-sm"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">
                        {LANGUAGES.find((x) => x.code === l.language)?.native}
                      </span>
                      <span className="text-xs text-muted">
                        until {fmt.date(l.expires_at)}
                      </span>
                    </div>
                    <div className="mt-1 truncate font-mono text-xs text-muted">
                      {url}
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-3">
                      <CopyButton text={url} label="Copy link" />
                      <a
                        href={`https://wa.me/${phone}?text=${encodeURIComponent(text)}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-brand hover:underline"
                      >
                        Send on WhatsApp
                      </a>
                      <Link
                        href={`/s/${l.token}`}
                        className="text-xs text-brand hover:underline"
                      >
                        Preview
                      </Link>
                      {can.enrol(ctx.role) && (
                        <form action={revokeStatementLink} className="ml-auto">
                          <input type="hidden" name="id" value={l.id} />
                          <input
                            type="hidden"
                            name="farmer_id"
                            value={farmer.id}
                          />
                          <button className="text-xs text-danger hover:underline">
                            Revoke
                          </button>
                        </form>
                      )}
                    </div>
                  </div>
                );
              })}
              {can.enrol(ctx.role) && (
                <ActionForm
                  action={createStatementLink}
                  submit="Create share link"
                  variant="secondary"
                  hidden={{ farmer_id: farmer.id }}
                >
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Language">
                      <Select name="language" defaultValue={farmer.language}>
                        {LANGUAGES.map((x) => (
                          <option key={x.code} value={x.code}>
                            {x.native}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Valid for (days)">
                      <Input
                        name="days"
                        type="number"
                        min={1}
                        max={365}
                        defaultValue={90}
                      />
                    </Field>
                  </div>
                </ActionForm>
              )}
              <p className="text-xs text-muted">
                Anyone with a link can read this statement until it expires or
                is revoked. It shows this farmer&apos;s own fields and payments,
                never anyone else&apos;s, and no boundaries or account numbers.
              </p>
            </div>
          </Card>
          <Card>
            <CardHeader title="Record" />
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 p-5 text-sm">
              <dt className="text-muted">Phone</dt>
              <dd>{farmer.phone ?? "—"}</dd>
              <dt className="text-muted">Consent</dt>
              <dd>
                {farmer.consent_on ? (
                  fmt.date(farmer.consent_on)
                ) : (
                  <Badge tone="accent">missing</Badge>
                )}
                {farmer.consent_reference && (
                  <div className="text-xs text-muted">
                    {farmer.consent_reference}
                  </div>
                )}
              </dd>
              <dt className="text-muted">Carbon rights</dt>
              <dd>
                {farmer.carbon_rights_ref ?? (
                  <Badge tone="accent">missing</Badge>
                )}
                {farmer.carbon_rights_signed_on && (
                  <div className="text-xs text-muted">
                    signed {fmt.date(farmer.carbon_rights_signed_on)}
                  </div>
                )}
              </dd>
              <dt className="text-muted">Payout</dt>
              <dd>
                {farmer.payout_method ?? "—"} {farmer.payout_reference}
              </dd>
              <dt className="text-muted">Language</dt>
              <dd>
                {LANGUAGES.find((x) => x.code === farmer.language)?.native ??
                  farmer.language}
              </dd>
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}
