import type { Metadata } from "next";
import Link from "next/link";

import { ActionForm } from "@/components/action-form";
import { Card, Field, Input } from "@/components/ui";
import { requestPasswordReset } from "@/lib/actions/auth";

export const metadata: Metadata = { title: "Reset password" };

export default function ForgotPage() {
  return (
    <Card className="p-6">
      <h1 className="text-lg font-semibold">Reset your password</h1>
      <p className="mt-1 text-sm text-muted">We&apos;ll email you a link to choose a new one.</p>
      <ActionForm action={requestPasswordReset} submit="Send reset link" className="mt-5">
        <Field label="Email">
          <Input name="email" type="email" autoComplete="email" required />
        </Field>
      </ActionForm>
      <p className="mt-6 text-center text-sm">
        <Link href="/login" className="text-muted underline">
          Back to sign in
        </Link>
      </p>
    </Card>
  );
}
