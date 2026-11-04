import type { Metadata } from "next";
import Link from "next/link";

import { ActionForm } from "@/components/action-form";
import { PasswordInput } from "@/components/password-input";
import { Button, Card, Field, Input, Notice } from "@/components/ui";
import { resendConfirmation, sendMagicLink, signIn, signInWithGoogle } from "@/lib/actions/auth";
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
  return (
    <Card className="p-6">
      <h1 className="text-lg font-semibold">Sign in</h1>
      <p className="mt-1 text-sm text-muted">Welcome back.</p>
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

      <ActionForm action={signIn} submit="Sign in" hidden={{ next }}>
        <Field label="Email">
          <Input name="email" type="email" autoComplete="email" required />
        </Field>
        <Field label="Password" hint={<Link href="/forgot" className="underline">Forgot it?</Link>}>
          <PasswordInput name="password" autoComplete="current-password" required />
        </Field>
      </ActionForm>

      <details className="mt-5 text-sm">
        <summary className="cursor-pointer text-muted">Email me a sign-in link instead</summary>
        <ActionForm action={sendMagicLink} submit="Send link" variant="secondary" className="mt-3" hidden={{ next }}>
          <Field label="Email">
            <Input name="email" type="email" autoComplete="email" required />
          </Field>
        </ActionForm>
      </details>

      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-muted">Didn&apos;t get your confirmation email?</summary>
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
  );
}
