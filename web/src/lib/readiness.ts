import type { Farm, Farmer, Project } from "@/lib/database.types";

// What a farm still needs before a verifier will credit it. The engine's own
// eligibility rules (carbonstack.domain / methodology.vm0051) decide in the
// end; this is the same list asked early, while the field agent is still on
// the farm and can fix it in minutes rather than a season later.

export type Check = { label: string; ok: boolean; fix: string };

export function readiness(farm: Farm, farmer: Farmer | null, project: Project | null): Check[] {
  const checks: Check[] = [
    {
      label: "Surveyed boundary",
      // Imports without a boundary arrive as drafts with a placeholder square.
      ok: farm.status !== "draft",
      fix: "This boundary was placed from a point and an area. Walk or draw the real one.",
    },
    { label: "Farmer linked", ok: !!farmer, fix: "Link the farmer who works this land." },
    {
      label: "Farmer consent recorded",
      ok: !!farmer?.consent_on && !!farmer.consent_reference,
      fix: "Record the date and reference of the farmer's signed consent.",
    },
    {
      label: "Carbon rights agreement",
      ok: !!farmer?.carbon_rights_ref,
      fix: "Attach the agreement that assigns the carbon rights to the project.",
    },
    {
      label: "Tenure documented",
      ok: !!farm.tenure && farm.tenure !== "undocumented" && !!farm.tenure_reference,
      fix: "Record the tenure basis and the reference of the land document.",
    },
    { label: "In a project", ok: !!farm.project_id, fix: "Add the farm to a project; it decides the methodology." },
  ];
  if (project?.pathway === "rice") {
    checks.push(
      {
        label: "Irrigated lowland rice",
        ok: farm.rice_ecosystem === "irrigated_lowland",
        fix: "VM0051 credits only irrigated lowland rice. Record the ecosystem.",
      },
      {
        label: "Drainage control",
        ok: farm.water_control === "full",
        fix: "AWD needs control of both irrigation and drainage. Record it.",
      },
      { label: "Crop calendar", ok: (farm.seasons?.length ?? 0) > 0, fix: "Add each season's sowing and harvest dates." },
    );
  }
  if (project?.pathway === "agroforestry") {
    checks.push({
      label: "Species and stems",
      ok: !!farm.species?.length && !!farm.stems_planted,
      fix: "Record which species were planted and how many stems.",
    });
  }
  return checks;
}

export function readyCount(checks: Check[]) {
  return { ok: checks.filter((c) => c.ok).length, total: checks.length };
}
