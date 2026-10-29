import type { Metadata } from "next";

import { ActionForm } from "@/components/action-form";
import { ProjectFields } from "@/components/record-fields";
import { Card, PageHeader } from "@/components/ui";
import { createProject } from "@/lib/actions/projects";

export const metadata: Metadata = { title: "New project" };

export default function NewProjectPage() {
  return (
    <>
      <PageHeader title="New project" crumbs={[{ href: "/app/projects", label: "Projects" }]} />
      <Card className="max-w-2xl p-6">
        <ActionForm action={createProject} submit="Create project">
          <ProjectFields />
        </ActionForm>
      </Card>
    </>
  );
}
