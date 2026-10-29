import type { Metadata } from "next";

import { ActionForm } from "@/components/action-form";
import { Card, Field, Input, PageHeader, Select } from "@/components/ui";
import { createFarmer } from "@/lib/actions/projects";

export const metadata: Metadata = { title: "Add a farmer" };

export default function NewFarmerPage() {
  return (
    <>
      <PageHeader title="Add a farmer" crumbs={[{ href: "/app/farmers", label: "Farmers" }]} />
      <Card className="max-w-3xl p-6">
        <ActionForm action={createFarmer} submit="Save farmer">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name">
              <Input name="name" required />
            </Field>
            <Field label="Your reference">
              <Input name="external_ref" placeholder="F-0042" />
            </Field>
            <Field label="Phone">
              <Input name="phone" type="tel" />
            </Field>
            <Field label="Village">
              <Input name="village" />
            </Field>
            <Field label="District">
              <Input name="district" />
            </Field>
            <Field label="State / county">
              <Input name="state" />
            </Field>
            <Field label="Country">
              <Input name="country" />
            </Field>
          </div>
          <h2 className="mt-2 text-sm font-semibold">Consent and rights</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Consent signed on">
              <Input name="consent_on" type="date" />
            </Field>
            <Field label="Consent reference">
              <Input name="consent_reference" />
            </Field>
            <Field label="Carbon rights agreement">
              <Input name="carbon_rights_ref" placeholder="CRA/2025/0042" />
            </Field>
            <Field label="Signed on">
              <Input name="carbon_rights_signed_on" type="date" />
            </Field>
          </div>
          <h2 className="mt-2 text-sm font-semibold">Payouts</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Method">
              <Select name="payout_method" defaultValue="">
                <option value="">Not set</option>
                <option value="upi">UPI</option>
                <option value="bank">Bank transfer</option>
                <option value="mobile_money">Mobile money</option>
                <option value="cash">Cash</option>
                <option value="other">Other</option>
              </Select>
            </Field>
            <Field label="Handle" hint="A masked handle only (e.g. ****4821). Never store full account numbers here.">
              <Input name="payout_reference" />
            </Field>
          </div>
        </ActionForm>
      </Card>
    </>
  );
}
