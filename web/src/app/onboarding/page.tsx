import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ActionForm } from "@/components/action-form";
import { Logo } from "@/components/logo";
import { Card, Field, Input, Select } from "@/components/ui";
import { signOut } from "@/lib/actions/auth";
import { createOrganization } from "@/lib/actions/org";
import { getUser } from "@/lib/data";
import { DEMO } from "@/lib/env";

export const metadata: Metadata = { title: "Set up your organisation" };

export default async function OnboardingPage() {
  if (DEMO) redirect("/app");
  const user = await getUser();
  if (!user) redirect("/login?next=/onboarding");
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 py-10">
      <div className="mb-8">
        <Logo />
      </div>
      <Card className="w-full max-w-md p-6">
        <h1 className="text-lg font-semibold">Set up your organisation</h1>
        <p className="mt-1 text-sm text-muted">
          Farms, farmers and credits belong to an organisation. You&apos;ll be its owner and can invite your team
          next. Joining an existing one? Open the invitation link you were sent.
        </p>
        <ActionForm action={createOrganization} submit="Create organisation" className="mt-5">
          <Field label="Organisation name">
            <Input name="name" placeholder="e.g. Cauvery Farmers Collective" required />
          </Field>
          <Field label="What you do">
            <Select name="kind" defaultValue="developer">
              <option value="developer">Project developer</option>
              <option value="aggregator">Farmer aggregator / FPO</option>
              <option value="buyer">Credit buyer</option>
              <option value="verifier">Verifier / auditor</option>
            </Select>
          </Field>
          <Field label="Country">
            <Input name="country" placeholder="India" />
          </Field>
        </ActionForm>
      </Card>
      <form action={signOut} className="mt-4">
        <button className="text-sm text-muted underline">Sign out ({user.email})</button>
      </form>
    </div>
  );
}
