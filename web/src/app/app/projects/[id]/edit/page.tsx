import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/action-form";
import { ProjectFields } from "@/components/record-fields";
import { Card, Notice, PageHeader } from "@/components/ui";
import { updateProject } from "@/lib/actions/projects";
import { getOrgContext, getProject } from "@/lib/data";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Edit project" };

export default async function EditProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ctx = await getOrgContext();
  const project = await getProject(ctx.org.id, id);
  if (!project) notFound();
  return (
    <>
      <PageHeader
        title={`Edit ${project.name}`}
        crumbs={[
          { href: "/app/projects", label: "Projects" },
          { href: `/app/projects/${project.id}`, label: project.name },
        ]}
      />
      {!can.manage(ctx.role) ? (
        <Notice tone="accent">Only analysts, admins and owners can edit projects.</Notice>
      ) : (
        <Card className="max-w-2xl p-6">
          <ActionForm action={updateProject} submit="Save changes" hidden={{ id: project.id }}>
            <ProjectFields project={project} />
          </ActionForm>
        </Card>
      )}
    </>
  );
}
