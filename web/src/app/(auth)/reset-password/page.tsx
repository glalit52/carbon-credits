import type { Metadata } from "next";

import { ActionForm } from "@/components/action-form";
import { PasswordInput } from "@/components/password-input";
import { Card, Field } from "@/components/ui";
import { resetPassword } from "@/lib/actions/auth";
import { PASSWORD_MIN } from "@/lib/auth-shared";
import { requireUser } from "@/lib/data";

export const metadata: Metadata = { title: "Choose a new password" };

/** Where a reset link lands, already signed in by the link itself. */
export default async function ResetPasswordPage() {
  const user = await requireUser("/reset-password");
  return (
    <Card className="p-6">
      <h1 className="text-lg font-semibold">Choose a new password</h1>
      <p className="mt-1 text-sm text-muted">
        For <strong>{user.email}</strong>. Other devices are signed out once it is set.
      </p>
      <ActionForm action={resetPassword} submit="Set password" className="mt-5">
        <Field label="New password" hint={`At least ${PASSWORD_MIN} characters.`}>
          <PasswordInput name="password" autoComplete="new-password" minLength={PASSWORD_MIN} required autoFocus />
        </Field>
        <Field label="Confirm new password">
          <PasswordInput name="confirm_password" autoComplete="new-password" minLength={PASSWORD_MIN} required />
        </Field>
      </ActionForm>
    </Card>
  );
}
