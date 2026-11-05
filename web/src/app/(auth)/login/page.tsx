import { Sparkles } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { ActionForm } from "@/components/action-form";
import { PasswordInput } from "@/components/password-input";
import { Badge, Button, Card, Field, Input, Notice } from "@/components/ui";
import { quickMockSignIn, resendConfirmation, sendMagicLink, signIn, signInWithGoogle } from "@/lib/actions/auth";
import { notice } from "@/lib/auth-shared";
import { GOOGLE_SIGN_IN } from "@/lib/env";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string; notice?: string }>;
}) {
  const { next, error, notice: code } = await searchParams;
  const said = notice(code);

  const mainMockRoles = [
    {
      email: "admin@carbonstack.io",
      label: "👑 Owner / Admin",
      name: "Priya Raman",
      desc: "Full administrative & issuance signing authority",
      role: "owner",
    },
    {
      email: "analyst@carbonstack.io",
      label: "📊 Carbon Analyst",
      name: "Ravi Shankar",
      desc: "MRV calculations, estimates & GIS data modeling",
      role: "analyst",
    },
    {
      email: "verifier@carbonstack.io",
      label: "🔍 4-Eyes Verifier",
      name: "Anjali Iyer",
      desc: "Telemetry evidence review & vintage audit approval",
      role: "reviewer",
    },
    {
      email: "field@carbonstack.io",
      label: "🌾 Field Agent",
      name: "Muthu Kumar",
      desc: "GPS boundary walks & farmer consent verification",
      role: "field_agent",
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <Card className="p-6 shadow-sm">
        <h1 className="text-xl font-semibold">Sign in</h1>
        <p className="mt-1 text-sm text-muted">Welcome back to carbonstack dMRV platform.</p>

        {said && (
          <div className="mt-4">
            <Notice tone="brand">{said}</Notice>
          </div>
        )}
        {error && (
          <div className="mt-4">
            <Notice tone="danger">{error}</Notice>
          </div>
        )}

        {GOOGLE_SIGN_IN && (
          <>
            <form action={signInWithGoogle} className="mt-5">
              <input type="hidden" name="next" value={next ?? ""} />
              <Button type="submit" variant="secondary" className="w-full">
                Continue with Google
              </Button>
            </form>

            <div className="my-5 flex items-center gap-3 text-xs text-muted">
              <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
            </div>
          </>
        )}

        <ActionForm action={signIn} submit="Sign in" hidden={{ next }} className="mt-5">
          <Field label="Email">
            <Input name="email" type="email" autoComplete="email" defaultValue="admin@carbonstack.io" required />
          </Field>
          <Field label="Password" hint={<Link href="/forgot" className="underline text-xs">Forgot it?</Link>}>
            <PasswordInput name="password" defaultValue="CarbonStack2026!" autoComplete="current-password" required />
          </Field>
        </ActionForm>

        <details className="mt-5 text-sm">
          <summary className="cursor-pointer text-muted text-xs">Email me a sign-in link instead</summary>
          <ActionForm action={sendMagicLink} submit="Send link" variant="secondary" className="mt-3" hidden={{ next }}>
            <Field label="Email">
              <Input name="email" type="email" autoComplete="email" required />
            </Field>
          </ActionForm>
        </details>

        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-muted text-xs">Didn&apos;t get your confirmation email?</summary>
          <ActionForm action={resendConfirmation} submit="Send it again" variant="secondary" className="mt-3" hidden={{ next }}>
            <Field label="Email">
              <Input name="email" type="email" autoComplete="email" required />
            </Field>
          </ActionForm>
        </details>

        <p className="mt-6 text-center text-sm text-muted">
          New here?{" "}
          <Link href={`/signup${next ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-medium text-brand">
            Create an account
          </Link>
        </p>
      </Card>

      {/* Mock Credentials & 1-Click Persona Sign-In Card */}
      <Card className="p-5 border-brand/40 bg-surface-2/40">
        <div className="flex items-center justify-between pb-3 border-b border-border">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand" />
            <span className="text-xs font-semibold uppercase tracking-wider text-text">
              1-Click Mock Credentials
            </span>
          </div>
          <Badge tone="brand">Production & Demo Ready</Badge>
        </div>

        <p className="text-xs text-muted mt-2">
          Test any role instantly without setup. Password for all mock accounts:{" "}
          <code className="font-mono font-semibold text-text bg-surface px-1.5 py-0.5 rounded border border-border">
            CarbonStack2026!
          </code>
        </p>

        <div className="mt-3.5 grid gap-2">
          {mainMockRoles.map((role) => (
            <form key={role.email} action={quickMockSignIn}>
              <input type="hidden" name="email" value={role.email} />
              <input type="hidden" name="next" value={next ?? "/app"} />
              <button
                type="submit"
                className="w-full flex items-center justify-between p-2.5 rounded-lg border border-border bg-surface hover:border-brand hover:bg-brand-soft/40 transition group text-left cursor-pointer shadow-2xs"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-text group-hover:text-brand transition">
                      {role.label}
                    </span>
                    <span className="text-[11px] text-muted">({role.name})</span>
                  </div>
                  <div className="text-[11px] text-muted font-mono">{role.email}</div>
                </div>
                <span className="text-xs font-medium text-brand group-hover:translate-x-0.5 transition shrink-0 ml-2">
                  Sign in →
                </span>
              </button>
            </form>
          ))}
        </div>
      </Card>
    </div>
  );
}
