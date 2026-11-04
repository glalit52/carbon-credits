import type { Metadata } from "next";
import Link from "next/link";

import { ActionForm } from "@/components/action-form";
import { PasswordInput } from "@/components/password-input";
import { Button, Card, Field, Input } from "@/components/ui";
import { signInWithGoogle, signUp } from "@/lib/actions/auth";
import { PASSWORD_MIN } from "@/lib/auth-shared";
import { GOOGLE_SIGN_IN } from "@/lib/env";

export const metadata: Metadata = { title: "Create an account" };

export default async function SignupPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return (
    <Card className="p-6">
      <h1 className="text-lg font-semibold">Create your account</h1>
      <p className="mt-1 text-sm text-muted">
        You&apos;ll set up your organisation next, or join one you were invited to.
      </p>

      {GOOGLE_SIGN_IN && (
        <>
          <form action={signInWithGoogle} className="mt-5">
            <input type="hidden" name="next" value={next ?? "/onboarding"} />
            <Button type="submit" variant="secondary" className="w-full">
              Sign up with Google
            </Button>
          </form>

          <div className="my-5 flex items-center gap-3 text-xs text-muted">
            <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
          </div>
        </>
      )}

      <ActionForm action={signUp} submit="Create account" hidden={{ next }}>
        <Field label="Your name">
          <Input name="full_name" autoComplete="name" maxLength={120} required />
        </Field>
        <Field label="Work email">
          <Input name="email" type="email" autoComplete="email" required />
        </Field>
        <Field label="Password" hint={`At least ${PASSWORD_MIN} characters.`}>
          <PasswordInput name="password" autoComplete="new-password" minLength={PASSWORD_MIN} required />
        </Field>
        <Field label="Confirm password">
          <PasswordInput name="confirm_password" autoComplete="new-password" minLength={PASSWORD_MIN} required />
        </Field>
      </ActionForm>

      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href={`/login${next ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-medium text-brand">
          Sign in
        </Link>
      </p>
    </Card>
  );
}
