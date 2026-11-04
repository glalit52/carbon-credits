import type { Metadata } from "next";

import { FarmForm } from "@/components/farm-form";
import { Notice, PageHeader } from "@/components/ui";
import { getOrgContext, listFarmers, listProjects } from "@/lib/data";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Add a farm" };

export default async function NewFarmPage() {
  const ctx = await getOrgContext();
  const [projects, farmers] = await Promise.all([listProjects(ctx.org.id), listFarmers(ctx.org.id)]);
  return (
    <>
      <PageHeader
        title="Add a farm"
        crumbs={[{ href: "/app/farms", label: "Farms" }]}
        description="Every boundary is checked as you go: closed, not crossing itself, a plausible size. The same checks run again when it is saved."
      />
      {!can.enrol(ctx.role) ? (
        <Notice tone="accent">Your role is read-only. Ask an admin to make you a field agent or analyst.</Notice>
      ) : (
        <FarmForm projects={projects} farmers={farmers} />
      )}
    </>
  );
}
