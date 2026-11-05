import { LogOut, MonitorSmartphone } from "lucide-react";
import type { Metadata } from "next";

import { ActionForm } from "@/components/action-form";
import { PasswordInput } from "@/components/password-input";
import { ProfileNav } from "@/components/profile/profile-nav";
import { Badge, Button, ButtonLink, Card, CardHeader, Field, Input, Notice, PageHeader } from "@/components/ui";
import {
  changeEmail,
  changePassword,
  deleteAccount,
  emailMeAResetLink,
  signOutEverywhere,
  signOutOtherDevices,
  updateProfile,
} from "@/lib/actions/auth";
import { leaveOrganization, switchOrganization } from "@/lib/actions/org";
import { PASSWORD_MIN, notice } from "@/lib/auth-shared";
import { getAccount, getOrgContext } from "@/lib/data";
import { fmt } from "@/lib/format";
import { ROLE_LABEL } from "@/lib/roles";

export const metadata: Metadata = { title: "Your profile" };

const PROVIDER_LABEL: Record<string, string> = { email: "Email", google: "Google" };
const KIND_LABEL: Record<string, string> = {
  developer: "Project developer",
  aggregator: "Farmer aggregator / FPO",
  buyer: "Credit buyer",
  verifier: "Verifier / auditor",
};

function initials(name: string | null, email: string | null): string {
  const words = (name ?? email ?? "?").split(/[\s@._-]+/).filter(Boolean);
  return words.slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "?";
}

export default async function ProfilePage({ searchParams }: { searchParams: Promise<{ notice?: string }> }) {
  const said = notice((await searchParams).notice);
  const [account, ctx] = await Promise.all([getAccount(), getOrgContext()]);
  const hasPassword = account.providers.includes("email");

  return (
    <>
      <PageHeader title="Your profile" description="How you sign in, what your teammates see, and the organisations you belong to." />
      <ProfileNav />
      {said && (
        <div className="mb-6">
          <Notice tone="brand">{said}</Notice>
        </div>
      )}

      <Card className="mb-6 flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
        <div
          aria-hidden
          className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-brand-soft text-lg font-semibold text-brand-strong"
        >
          {initials(account.name, account.email)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-lg font-semibold">{account.name ?? "Unnamed"}</div>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
            <span className="truncate">{account.email}</span>
            {account.email_confirmed ? <Badge tone="brand">Verified</Badge> : <Badge tone="accent">Unverified</Badge>}
            {account.providers.map((p) => (
              <Badge key={p}>{PROVIDER_LABEL[p] ?? p}</Badge>
            ))}
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:text-right">
          <dt className="text-muted">Member since</dt>
          <dd className="tabular">{fmt.date(account.created_at)}</dd>
          <dt className="text-muted">Last sign-in</dt>
          <dd className="tabular">{fmt.datetime(account.last_sign_in_at)}</dd>
        </dl>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader title="Personal details" description="Your name and phone are shown to people in your organisations." />
            <div className="p-5">
              <ActionForm action={updateProfile} submit="Save profile" variant="secondary" className="sm:max-w-md">
                <Field label="Your name">
                  <Input name="full_name" defaultValue={account.name ?? ""} autoComplete="name" maxLength={120} required />
                </Field>
                <Field label="Phone" hint="With the country code, e.g. +91 98765 43210.">
                  <Input name="phone" type="tel" defaultValue={account.phone ?? ""} autoComplete="tel" />
                </Field>
              </ActionForm>
            </div>
          </Card>

          <Card>
            <CardHeader title="Email address" description={`You sign in with ${account.email ?? "no email"}.`} />
            <div className="flex flex-col gap-4 p-5">
              {account.pending_email && (
                <Notice tone="info" title="Change waiting for confirmation">
                  Open the link sent to <strong>{account.pending_email}</strong> to finish switching to it.
                </Notice>
              )}
              <ActionForm action={changeEmail} submit="Change email" variant="secondary" className="sm:max-w-md">
                <Field label="New email">
                  <Input name="email" type="email" autoComplete="email" required />
                </Field>
              </ActionForm>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Password"
              description={
                hasPassword
                  ? "Changing it signs you out on every other device."
                  : "You sign in with Google. Set a password to sign in with your email too."
              }
            />
            <div className="flex flex-col gap-5 p-5">
              <ActionForm
                action={changePassword}
                submit={hasPassword ? "Change password" : "Set password"}
                variant="secondary"
                className="sm:max-w-md"
              >
                {hasPassword && (
                  <Field label="Current password">
                    <PasswordInput name="current_password" autoComplete="current-password" required />
                  </Field>
                )}
                <Field label="New password" hint={`At least ${PASSWORD_MIN} characters.`}>
                  <PasswordInput name="password" autoComplete="new-password" minLength={PASSWORD_MIN} required />
                </Field>
                <Field label="Confirm new password">
                  <PasswordInput name="confirm_password" autoComplete="new-password" minLength={PASSWORD_MIN} required />
                </Field>
              </ActionForm>
              {hasPassword && (
                <details className="text-sm">
                  <summary className="cursor-pointer text-muted">
                    Forgot your current password, or only ever signed in with an email link?
                  </summary>
                  <ActionForm
                    action={emailMeAResetLink}
                    submit="Email me a link to set a new one"
                    variant="secondary"
                    className="mt-3 sm:max-w-md"
                  />
                </details>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Your organisations"
              description="Each keeps its own farms, credits and team. Your role is set by its admins."
              action={
                <ButtonLink href="/onboarding" variant="secondary" className="py-1.5 text-xs">
                  New organisation
                </ButtonLink>
              }
            />
            <ul className="divide-y divide-border">
              {ctx.orgs.map(({ org, role }) => (
                <li key={org.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 font-medium">
                      {org.name}
                      {org.id === ctx.org.id && <Badge tone="brand">Current</Badge>}
                    </div>
                    <div className="text-sm text-muted">
                      {ROLE_LABEL[role]} · {KIND_LABEL[org.kind] ?? org.kind}
                      {org.country ? ` · ${org.country}` : ""}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-start gap-2">
                    {org.id !== ctx.org.id && (
                      <form action={switchOrganization}>
                        <input type="hidden" name="org_id" value={org.id} />
                        <Button variant="secondary" className="py-1.5 text-xs" disabled={ctx.demo}>
                          Switch to
                        </Button>
                      </form>
                    )}
                    <ActionForm
                      action={leaveOrganization}
                      submit="Leave"
                      variant="ghost"
                      hidden={{ org_id: org.id }}
                      className="gap-2 sm:max-w-xs"
                      submitClassName="py-1.5 text-xs text-danger"
                    />
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader title="Sessions" description="Where you are signed in." />
            <div className="flex flex-col gap-4 p-5 text-sm">
              <p className="flex items-start gap-2 text-muted">
                <MonitorSmartphone className="mt-0.5 h-4 w-4 shrink-0" />
                Left a shared field phone signed in? Sign the others out and stay signed in here.
              </p>
              <ActionForm action={signOutOtherDevices} submit="Sign out other devices" variant="secondary" />
              <form action={signOutEverywhere}>
                <Button variant="ghost" className="w-full" disabled={ctx.demo}>
                  <LogOut className="h-4 w-4" /> Sign out everywhere, including here
                </Button>
              </form>
            </div>
          </Card>

          <Card className="border-danger/40">
            <CardHeader title="Close your account" />
            <div className="flex flex-col gap-4 p-5 text-sm">
              <p className="text-muted">
                Your login and profile are deleted. Farms, credits and payments you recorded stay with their
                organisation, and the audit log keeps what you did. If you are the only owner of an
                organisation, make someone else an owner first.
              </p>
              <ActionForm action={deleteAccount} submit="Close my account" variant="danger">
                <Field label={`Type ${account.email ?? "your email"} to confirm`}>
                  <Input name="confirm_email" type="email" autoComplete="off" required />
                </Field>
              </ActionForm>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
