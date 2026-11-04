import type { Metadata } from "next";
import Link from "next/link";

import { ActionForm } from "@/components/action-form";
import { Button, Card, Field, Input } from "@/components/ui";
import { signInWithGoogle, signUp } from "@/lib/actions/auth";

export const metadata: Metadata = { title: "Create an account" };

export default async function SignupPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return (
    <Card className="p-6">
      <h1 className="text-lg font-semibold">Create your account</h1>
      <p className="mt-1 text-sm text-muted">
        You&apos;ll set up your organisation next, or join one you were invited to.
      </p>

      <form action={signInWithGoogle} className="mt-5">
        <input type="hidden" name="next" value={next ?? "/onboarding"} />
        <Button type="submit" variant="secondary" className="w-full">
          Sign up with Google
        </Button>
      </form>

      <div className="my-5 flex items-center gap-3 text-xs text-muted">
        <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
      </div>

      <ActionForm action={signUp} submit="Create account" hidden={{ next }}>
        <Field label="Your name">
          <Input name="full_name" autoComplete="name" required />
        </Field>
        <Field label="Work email">
          <Input name="email" type="email" autoComplete="email" required />
        </Field>
        <Field label="Password" hint="At least 10 characters.">
          <Input name="password" type="password" autoComplete="new-password" minLength={10} required />
        </Field>
      </ActionForm>

      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-brand">
          Sign in
        </Link>
      </p>
    </Card>
  );
}
