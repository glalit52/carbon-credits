"use client";

import { Plus, X } from "lucide-react";
import { useActionState, useMemo, useState } from "react";

import type { Farm, Farmer, Project, Season } from "@/lib/database.types";
import { createFarm, updateFarm } from "@/lib/actions/farms";
import { TENURE_LABEL } from "@/lib/format";

import { BoundaryEditor } from "./map/boundary-editor";
import { Button, Card, CardHeader, Field, Input, Notice, Select } from "./ui";

type SeasonRow = { name: string; start: string; end: string };

const RICE_DEFAULT: SeasonRow[] = [{ name: "Kharif", start: "06-15", end: "10-15" }];

function serialise(rows: SeasonRow[]): string {
  return rows
    .filter((r) => r.start && r.end)
    .map((r) => `${r.name || "Season"}:${r.start}/${r.end}`)
    .join(";");
}

const mmdd = (m: number, d: number) => `${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
const toRows = (s: Season[]): SeasonRow[] =>
  s.map((x) => ({ name: x.name, start: mmdd(x.start_month, x.start_day), end: mmdd(x.end_month, x.end_day) }));

/** Adds a farm, or edits one when `farm` is given. */
export function FarmForm({ projects, farmers, farm }: { projects: Project[]; farmers: Farmer[]; farm?: Farm }) {
  const [state, action, pending] = useActionState(farm ? updateFarm : createFarm, {});
  const [projectId, setProjectId] = useState(farm ? (farm.project_id ?? "") : (projects[0]?.id ?? ""));
  const [farmerId, setFarmerId] = useState(farm ? (farm.farmer_id ?? "") : farmers.length ? "" : "new");
  const [seasons, setSeasons] = useState<SeasonRow[]>(farm?.seasons?.length ? toRows(farm.seasons) : RICE_DEFAULT);
  const pathway = useMemo(() => projects.find((p) => p.id === projectId)?.pathway, [projects, projectId]);

  return (
    <form action={action} className="grid gap-6 lg:grid-cols-5">
      {farm && <input type="hidden" name="id" value={farm.id} />}
      <Card className="lg:col-span-3">
        <CardHeader title="Boundary" description="Draw it on imagery, walk it with a phone, paste corner points, or upload a file." />
        <div className="p-5">
          <BoundaryEditor initial={farm?.boundary} />
        </div>
      </Card>

      <div className="flex flex-col gap-6 lg:col-span-2">
        <Card>
          <CardHeader title="Farm" />
          <div className="grid gap-4 p-5 sm:grid-cols-2">
            <Field label="Name" className="sm:col-span-2">
              <Input name="name" required placeholder="e.g. Murugan — north field" defaultValue={farm?.name} />
            </Field>
            <Field label="Your reference" hint="Optional; must be unique.">
              <Input name="external_ref" placeholder="TNJ-0042" defaultValue={farm?.external_ref ?? ""} />
            </Field>
            <Field label="Enrolled on">
              <Input name="enrolled_on" type="date" defaultValue={farm ? (farm.enrolled_on ?? "") : new Date().toISOString().slice(0, 10)} />
            </Field>
            <Field label="Project" className="sm:col-span-2" hint={pathway ? `Pathway: ${pathway}` : undefined}>
              <Select name="project_id" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                <option value="">No project yet</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.methodology})
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Crop">
              <Input name="crop" placeholder={pathway === "rice" ? "Paddy rice" : "Coffee under shade"} defaultValue={farm?.crop ?? ""} />
            </Field>
            <Field label="Practice">
              <Input name="practice" defaultValue={farm ? (farm.practice ?? "") : pathway === "rice" ? "awd" : pathway === "agroforestry" ? "shade_trees" : ""} />
            </Field>
          </div>
        </Card>

        <Card>
          <CardHeader title="Farmer" />
          <div className="flex flex-col gap-4 p-5">
            <Select name="farmer_id" value={farmerId} onChange={(e) => setFarmerId(e.target.value)}>
              <option value="">Not linked yet</option>
              <option value="new">+ New farmer</option>
              {farmers.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                  {f.village ? ` · ${f.village}` : ""}
                </option>
              ))}
            </Select>
            {farmerId === "new" && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Farmer's name" className="sm:col-span-2">
                  <Input name="new_farmer_name" required />
                </Field>
                <Field label="Phone">
                  <Input name="new_farmer_phone" type="tel" />
                </Field>
                <Field label="Village">
                  <Input name="new_farmer_village" />
                </Field>
                <Field label="Consent signed on">
                  <Input name="consent_on" type="date" />
                </Field>
                <Field label="Consent reference">
                  <Input name="consent_reference" placeholder="Form no. / photo id" />
                </Field>
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Land and eligibility" />
          <div className="grid gap-4 p-5 sm:grid-cols-2">
            <Field label="Tenure basis">
              <Select name="tenure" defaultValue={farm?.tenure ?? ""}>
                <option value="">Not recorded</option>
                {Object.entries(TENURE_LABEL).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Land document reference">
              <Input name="tenure_reference" placeholder="Patta / title / lease no." defaultValue={farm?.tenure_reference ?? ""} />
            </Field>

            {pathway === "rice" && (
              <>
                <Field label="Rice ecosystem" hint="VM0051 credits irrigated lowland only.">
                  <Select name="rice_ecosystem" defaultValue={farm?.rice_ecosystem ?? "irrigated_lowland"}>
                    <option value="irrigated_lowland">Irrigated lowland</option>
                    <option value="rainfed">Rainfed</option>
                    <option value="upland">Upland</option>
                    <option value="deepwater">Deepwater</option>
                    <option value="unknown">Unknown</option>
                  </Select>
                </Field>
                <Field label="Water control" hint="AWD needs control of drainage.">
                  <Select name="water_control" defaultValue={farm?.water_control ?? "full"}>
                    <option value="full">Irrigation and drainage</option>
                    <option value="irrigation_only">Irrigation only</option>
                    <option value="none">None</option>
                    <option value="unknown">Unknown</option>
                  </Select>
                </Field>
                <div className="flex flex-col gap-2 sm:col-span-2">
                  <span className="text-sm font-medium">Crop calendar</span>
                  <input type="hidden" name="seasons" value={serialise(seasons)} />
                  {seasons.map((s, i) => (
                    <div key={i} className="grid grid-cols-[1fr_5rem_5rem_auto] items-center gap-2">
                      <Input
                        value={s.name}
                        aria-label="Season name"
                        onChange={(e) => setSeasons(seasons.map((r, j) => (j === i ? { ...r, name: e.target.value } : r)))}
                      />
                      <Input
                        value={s.start}
                        aria-label="Starts (MM-DD)"
                        placeholder="06-15"
                        pattern="\d{2}-\d{2}"
                        onChange={(e) => setSeasons(seasons.map((r, j) => (j === i ? { ...r, start: e.target.value } : r)))}
                      />
                      <Input
                        value={s.end}
                        aria-label="Ends (MM-DD)"
                        placeholder="10-15"
                        pattern="\d{2}-\d{2}"
                        onChange={(e) => setSeasons(seasons.map((r, j) => (j === i ? { ...r, end: e.target.value } : r)))}
                      />
                      <button
                        type="button"
                        aria-label="Remove season"
                        className="rounded p-1 text-muted hover:bg-surface-2"
                        onClick={() => setSeasons(seasons.filter((_, j) => j !== i))}
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="flex items-center gap-1 self-start text-xs font-medium text-brand"
                    onClick={() => setSeasons([...seasons, { name: "", start: "", end: "" }])}
                  >
                    <Plus className="h-3.5 w-3.5" /> Add season
                  </button>
                  <span className="text-xs text-muted">Sowing and harvest as month-day. A season may run past New Year.</span>
                </div>
              </>
            )}

            {pathway === "agroforestry" && (
              <>
                <Field label="Species" hint="Comma separated." className="sm:col-span-2">
                  <Input name="species" placeholder="Grevillea robusta, Cordia africana" defaultValue={farm?.species?.join(", ") ?? ""} />
                </Field>
                <Field label="Stems planted">
                  <Input name="stems_planted" type="number" min={0} defaultValue={farm?.stems_planted ?? ""} />
                </Field>
              </>
            )}
          </div>
        </Card>

        {state.error && <Notice tone="danger">{state.error}</Notice>}
        <Button type="submit" disabled={pending} className="py-2.5">
          {pending ? "Saving…" : farm ? "Save changes" : "Save farm"}
        </Button>
      </div>
    </form>
  );
}
