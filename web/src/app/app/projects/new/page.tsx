import type { Metadata } from "next";

import { ActionForm } from "@/components/action-form";
import { Card, Field, Input, PageHeader, Select } from "@/components/ui";
import { createProject } from "@/lib/actions/projects";

export const metadata: Metadata = { title: "New project" };

export default function NewProjectPage() {
  return (
    <>
      <PageHeader title="New project" crumbs={[{ href: "/app/projects", label: "Projects" }]} />
      <Card className="max-w-2xl p-6">
        <ActionForm action={createProject} submit="Create project">
          <Field label="Name">
            <Input name="name" required placeholder="e.g. Cauvery Delta AWD" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Pathway" hint="The engine estimates rice and agroforestry today.">
              <Select name="pathway" defaultValue="rice">
                <option value="rice">Rice methane (AWD) — VM0051</option>
                <option value="agroforestry">Agroforestry / ARR — VM0047</option>
                <option value="soil">Soil carbon — VM0042</option>
                <option value="other">Other</option>
              </Select>
            </Field>
            <Field label="Methodology" hint="Defaults from the pathway.">
              <Input name="methodology" placeholder="VM0051" />
            </Field>
            <Field label="Registry">
              <Select name="registry" defaultValue="Verra">
                <option>Verra</option>
                <option>Gold Standard</option>
                <option>Puro.earth</option>
                <option>Isometric</option>
                <option value="">Not decided</option>
              </Select>
            </Field>
            <Field label="Crediting period (years)">
              <Input name="crediting_period_yrs" type="number" min={1} max={100} defaultValue={7} />
            </Field>
            <Field label="Country">
              <Input name="country" />
            </Field>
            <Field label="Region">
              <Input name="region" />
            </Field>
            <Field label="Start date">
              <Input name="start_date" type="date" />
            </Field>
          </div>
        </ActionForm>
      </Card>
    </>
  );
}
