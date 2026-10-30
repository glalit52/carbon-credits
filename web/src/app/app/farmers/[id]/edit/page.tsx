import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/action-form";
import { FarmerFields } from "@/components/record-fields";
import { Card, Notice, PageHeader } from "@/components/ui";
import { updateFarmer } from "@/lib/actions/projects";
import { getFarmer, getOrgContext } from "@/lib/data";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Edit farmer" };

export default async function EditFarmerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ctx = await getOrgContext();
  const farmer = await getFarmer(ctx.org.id, id);
  if (!farmer) notFound();
  return (
    <>
      <PageHeader
        title={`Edit ${farmer.name}`}
        crumbs={[
          { href: "/app/farmers", label: "Farmers" },
          { href: `/app/farmers/${farmer.id}`, label: farmer.name },
        ]}
      />
      {!can.enrol(ctx.role) ? (
        <Notice tone="accent">Your role is read-only.</Notice>
      ) : (
        <Card className="max-w-3xl p-6">
          <ActionForm action={updateFarmer} submit="Save changes" hidden={{ id: farmer.id }}>
            <FarmerFields farmer={farmer} />
          </ActionForm>
        </Card>
      )}
    </>
  );
}
