import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { FarmForm } from "@/components/farm-form";
import { Notice, PageHeader } from "@/components/ui";
import { getFarm, getOrgContext, listFarmers, listProjects } from "@/lib/data";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Edit farm" };

export default async function EditFarmPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ctx = await getOrgContext();
  const farm = await getFarm(ctx.org.id, id);
  if (!farm) notFound();
  const [projects, farmers] = await Promise.all([listProjects(ctx.org.id), listFarmers(ctx.org.id)]);
  return (
    <>
      <PageHeader
        title={`Edit ${farm.name}`}
        crumbs={[
          { href: "/app/farms", label: "Farms" },
          { href: `/app/farms/${farm.id}`, label: farm.name },
        ]}
        description="Drag corners on the map to correct the boundary, or replace it from any of the four sources. Redrawing a draft farm's boundary enrols it."
      />
      {!can.enrol(ctx.role) ? (
        <Notice tone="accent">Your role is read-only.</Notice>
      ) : (
        <FarmForm projects={projects} farmers={farmers} farm={farm} />
      )}
    </>
  );
}
