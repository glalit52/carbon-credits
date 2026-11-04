import type { Metadata } from "next";

import { PageHeader } from "@/components/ui";
import { getOrgContext, listProjects } from "@/lib/data";

import { ReconcileForm } from "./reconcile-form";

export const metadata: Metadata = { title: "Registry reconciliation" };

export default async function RegistryPage() {
  const ctx = await getOrgContext();
  const projects = await listProjects(ctx.org.id);
  return (
    <>
      <PageHeader
        crumbs={[{ href: "/app/credits", label: "Credits" }]}
        title="Reconcile with the registry"
        description="The registry is the record of a credit; this ledger is the record of why it exists. They must agree to the tonne. Run this after every issuance and before every sale."
      />
      <ReconcileForm projects={projects.map((p) => ({ id: p.id, name: p.name }))} />
    </>
  );
}
