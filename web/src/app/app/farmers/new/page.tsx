import type { Metadata } from "next";

import { ActionForm } from "@/components/action-form";
import { FarmerFields } from "@/components/record-fields";
import { Card, PageHeader } from "@/components/ui";
import { createFarmer } from "@/lib/actions/projects";

export const metadata: Metadata = { title: "Add a farmer" };

export default function NewFarmerPage() {
  return (
    <>
      <PageHeader title="Add a farmer" crumbs={[{ href: "/app/farmers", label: "Farmers" }]} />
      <Card className="max-w-3xl p-6">
        <ActionForm action={createFarmer} submit="Save farmer">
          <FarmerFields />
        </ActionForm>
      </Card>
    </>
  );
}
