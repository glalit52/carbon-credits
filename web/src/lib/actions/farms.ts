"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import type {
  Database,
  Farm,
  Farmer,
  Project,
  FarmSource,
  Json,
  PolygonGeometry,
  RiceEcosystem,
  Season,
  Tenure,
  WaterControl,
} from "@/lib/database.types";
import { getOrgContext } from "@/lib/data";
import { EngineError, estimateRequest, runEstimate } from "@/lib/engine";
import { measure, validate } from "@/lib/geo";
import { parseSeasons } from "@/lib/import";
import { can } from "@/lib/roles";
import { supabaseServer } from "@/lib/supabase/server";

import { type ActionResult, explain, num, refuseInDemo, str } from "./result";

const TENURES: Tenure[] = ["owned_title", "registered_lease", "community_right", "grama_sabha_consent", "undocumented"];

function geometryFrom(form: FormData): { geometry?: PolygonGeometry; error?: string } {
  const raw = str(form, "boundary");
  if (!raw) return { error: "Draw, walk, paste or upload the farm's boundary first." };
  let geometry: PolygonGeometry;
  try {
    geometry = JSON.parse(raw);
  } catch {
    return { error: "The boundary could not be read; draw it again." };
  }
  if (geometry?.type !== "Polygon" && geometry?.type !== "MultiPolygon") {
    return { error: "The boundary must be a polygon." };
  }
  // The browser checked already; the server checks again because a form can
  // be posted without the browser.
  const problems = validate(geometry);
  return problems.length ? { error: `Boundary: ${problems.join("; ")}` } : { geometry };
}

function seasonsFrom(form: FormData): { seasons: Season[]; error?: string } {
  const errors: string[] = [];
  const seasons = parseSeasons(str(form, "seasons"), errors);
  return { seasons, error: errors[0] };
}

/** The farm fields a form carries, validated; shared by add and edit. */
function farmFields(form: FormData) {
  const name = str(form, "name");
  if (!name) return { error: "Give the farm a name." };
  const { geometry, error } = geometryFrom(form);
  if (!geometry) return { error };
  const { seasons, error: seasonError } = seasonsFrom(form);
  if (seasonError) return { error: seasonError };
  const tenure = str(form, "tenure") as Tenure | null;
  if (tenure && !TENURES.includes(tenure)) return { error: "Unknown tenure basis." };
  const species = str(form, "species")
    ?.split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return {
    fields: {
      project_id: str(form, "project_id"),
      name,
      external_ref: str(form, "external_ref"),
      boundary: geometry,
      ...measure(geometry),
      crop: str(form, "crop"),
      practice: str(form, "practice"),
      tenure,
      tenure_reference: str(form, "tenure_reference"),
      rice_ecosystem: str(form, "rice_ecosystem") as RiceEcosystem | null,
      water_control: str(form, "water_control") as WaterControl | null,
      stems_planted: num(form, "stems_planted"),
      species: species?.length ? species : null,
      enrolled_on: str(form, "enrolled_on"),
      seasons,
    },
  };
}

/** The chosen farmer, creating one first when the form asks for a new one. */
async function farmerFor(
  form: FormData,
  supabase: Awaited<ReturnType<typeof supabaseServer>>,
  orgId: string,
  userId: string,
): Promise<{ id: string | null; error?: string }> {
  const chosen = str(form, "farmer_id");
  if (chosen !== "new") return { id: chosen };
  const name = str(form, "new_farmer_name");
  if (!name) return { id: null, error: "Name the new farmer, or pick an existing one." };
  const { data, error } = await supabase
    .from("farmers")
    .insert({
      org_id: orgId,
      name,
      phone: str(form, "new_farmer_phone"),
      village: str(form, "new_farmer_village"),
      consent_on: str(form, "consent_on"),
      consent_reference: str(form, "consent_reference"),
      created_by: userId,
    })
    .select("id")
    .single();
  return error ? { id: null, error: explain(error.message) } : { id: data.id };
}

export async function createFarm(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.enrol(ctx.role)) return { error: "Your role cannot enrol farms." };
  const { fields, error } = farmFields(form);
  if (!fields) return { error };

  const supabase = await supabaseServer();
  const farmer = await farmerFor(form, supabase, ctx.org.id, ctx.user.id);
  if (farmer.error) return { error: farmer.error };
  const { data, error: insertError } = await supabase
    .from("farms")
    .insert({
      ...fields,
      org_id: ctx.org.id,
      farmer_id: farmer.id,
      source: (str(form, "source") as FarmSource | null) ?? "drawn",
      status: "enrolled",
      created_by: ctx.user.id,
    })
    .select("id")
    .single();
  if (insertError) return { error: explain(insertError.message) };
  revalidatePath("/app/farms");
  redirect(`/app/farms/${data.id}?created=1`);
}

export async function updateFarm(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.enrol(ctx.role)) return { error: "Your role cannot edit farms." };
  const id = str(form, "id");
  if (!id) return { error: "Missing farm." };
  const { fields, error } = farmFields(form);
  if (!fields) return { error };

  const supabase = await supabaseServer();
  const { data: before } = await supabase
    .from("farms")
    .select("boundary, status")
    .eq("id", id)
    .eq("org_id", ctx.org.id)
    .maybeSingle();
  if (!before) return { error: "Farm not found." };
  const farmer = await farmerFor(form, supabase, ctx.org.id, ctx.user.id);
  if (farmer.error) return { error: farmer.error };

  // A draft imported from a point becomes a real farm once someone redraws it.
  const redrawn = JSON.stringify(before.boundary) !== JSON.stringify(fields.boundary);
  const { error: updateError } = await supabase
    .from("farms")
    .update({
      ...fields,
      farmer_id: farmer.id,
      ...(redrawn ? { source: "drawn" as const } : {}),
      ...(redrawn && before.status === "draft" ? { status: "enrolled" as const } : {}),
    })
    .eq("id", id)
    .eq("org_id", ctx.org.id);
  if (updateError) return { error: explain(updateError.message) };
  revalidatePath(`/app/farms/${id}`);
  redirect(`/app/farms/${id}?saved=1`);
}

export async function updateFarmStatus(form: FormData): Promise<void> {
  if (refuseInDemo()) return;
  const id = str(form, "id");
  const status = str(form, "status") as Database["public"]["Tables"]["farms"]["Row"]["status"] | null;
  if (!id || !status) return;
  const ctx = await getOrgContext();
  const supabase = await supabaseServer();
  await supabase.from("farms").update({ status }).eq("id", id).eq("org_id", ctx.org.id);
  revalidatePath(`/app/farms/${id}`);
}

export async function deleteFarm(form: FormData): Promise<void> {
  if (refuseInDemo()) return;
  const id = str(form, "id");
  if (!id) return;
  const ctx = await getOrgContext();
  const supabase = await supabaseServer();
  await supabase.from("farms").delete().eq("id", id).eq("org_id", ctx.org.id);
  revalidatePath("/app/farms");
  redirect("/app/farms");
}

export async function addPractice(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  const farm_id = str(form, "farm_id");
  const year = num(form, "year");
  const practice = str(form, "practice");
  if (!farm_id || !year || !practice) return { error: "Year and practice are required." };
  const supabase = await supabaseServer();

  let evidence_path: string | null = null;
  const file = form.get("evidence");
  if (file instanceof File && file.size > 0) {
    if (file.size > 20 * 1024 * 1024) return { error: "Evidence files must be under 20 MB." };
    const safe = file.name.replace(/[^\w.-]+/g, "_").slice(-80);
    evidence_path = `${ctx.org.id}/farms/${farm_id}/${Date.now()}-${safe}`;
    const { error } = await supabase.storage.from("evidence").upload(evidence_path, file, {
      contentType: file.type || "application/octet-stream",
    });
    if (error) return { error: `Upload failed: ${explain(error.message)}` };
  }

  const { error } = await supabase.from("practice_records").insert({
    org_id: ctx.org.id,
    farm_id,
    year,
    season: str(form, "season"),
    practice,
    started_on: str(form, "started_on"),
    ended_on: str(form, "ended_on"),
    notes: str(form, "notes"),
    evidence_path,
    recorded_by: ctx.user.id,
  });
  if (error) return { error: explain(error.message) };
  revalidatePath(`/app/farms/${farm_id}`);
  return { message: "Practice recorded." };
}

export async function addSoilSample(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  const farm_id = str(form, "farm_id");
  const sampled_on = str(form, "sampled_on");
  const top = num(form, "depth_top_cm");
  const bottom = num(form, "depth_bottom_cm");
  const soc = num(form, "soc_pct");
  if (!farm_id || !sampled_on || top === null || bottom === null || soc === null) {
    return { error: "Date, depths and SOC are required." };
  }
  if (bottom <= top) return { error: "The bottom depth must be below the top depth." };
  const supabase = await supabaseServer();
  const { error } = await supabase.from("soil_samples").insert({
    org_id: ctx.org.id,
    farm_id,
    sampled_on,
    depth_top_cm: top,
    depth_bottom_cm: bottom,
    soc_pct: soc,
    bulk_density: num(form, "bulk_density"),
    lab: str(form, "lab"),
    lab_reference: str(form, "lab_reference"),
    recorded_by: ctx.user.id,
  });
  if (error) return { error: explain(error.message) };
  revalidatePath(`/app/farms/${farm_id}`);
  return { message: "Sample recorded." };
}

type Supabase = Awaited<ReturnType<typeof supabaseServer>>;

/** Run the engine for one farm and keep one estimate row per year. */
async function estimateOne(
  supabase: Supabase,
  orgId: string,
  userId: string,
  farm: Farm,
  project: Project,
  farmer: Farmer | null,
): Promise<string | null> {
  try {
    const request = estimateRequest(farm, farmer, project.pathway);
    const result = await runEstimate(request);
    const kept = result.vintages.filter((v) => v.net_t !== undefined);
    // The monitoring series covers the farm, not one year: keep it once, on
    // the latest year's row, rather than copying it onto every row.
    const { monitoring, ...rest } = result;
    const rows = kept.map((v, i) => ({
        org_id: orgId,
        farm_id: farm.id,
        year: v.year,
        methodology: result.methodology,
        gross_t: v.gross_t ?? 0,
        net_t: v.net_t ?? 0,
        data_quality: result.data_quality,
        input: request as unknown as Json,
        result: { ...rest, vintages: [v], ...(i === kept.length - 1 ? { monitoring } : {}) } as unknown as Json,
        engine_version: "carbonstack@estimate-v1",
        requested_by: userId,
      }));
    if (!rows.length) return "no season has closed since enrolment";
    const { error } = await supabase.from("estimates").insert(rows);
    return error ? explain(error.message) : null;
  } catch (e) {
    return e instanceof EngineError ? e.message : `estimate failed: ${(e as Error).message}`;
  }
}

export async function estimateFarm(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.enrol(ctx.role)) return { error: "Your role cannot run estimates." };
  const farm_id = str(form, "farm_id");
  if (!farm_id) return { error: "Missing farm." };
  const supabase = await supabaseServer();
  const { data: farm } = await supabase.from("farms").select("*").eq("id", farm_id).eq("org_id", ctx.org.id).maybeSingle();
  if (!farm) return { error: "Farm not found." };
  if (!farm.project_id) return { error: "Add the farm to a project first: the project decides the methodology." };
  const [{ data: project }, { data: farmer }] = await Promise.all([
    supabase.from("projects").select("*").eq("id", farm.project_id).single(),
    farm.farmer_id
      ? supabase.from("farmers").select("*").eq("id", farm.farmer_id).single()
      : Promise.resolve({ data: null }),
  ]);
  if (!project) return { error: "The farm's project could not be read." };
  const problem = await estimateOne(supabase, ctx.org.id, ctx.user.id, farm, project, farmer);
  if (problem) return { error: problem.charAt(0).toUpperCase() + problem.slice(1) + "." };
  revalidatePath(`/app/farms/${farm_id}`);
  revalidatePath("/app");
  return { message: "Estimate updated." };
}

/** One request's worth of farms: the engine call is seconds, not milliseconds. */
const PROJECT_BATCH = 60;

/**
 * Estimate every enrolled farm in a project, least recently estimated first,
 * four at a time. Large projects take several clicks; each one picks up where
 * the last left off because the stalest farms always go first.
 */
export async function estimateProject(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.manage(ctx.role)) return { error: "Only analysts, admins and owners run project-wide estimates." };
  const project_id = str(form, "project_id");
  if (!project_id) return { error: "Missing project." };
  const supabase = await supabaseServer();
  const [{ data: project }, { data: farms }, { data: farmers }, { data: latest }] = await Promise.all([
    supabase.from("projects").select("*").eq("id", project_id).eq("org_id", ctx.org.id).single(),
    supabase.from("farms").select("*").eq("project_id", project_id).eq("status", "enrolled"),
    supabase.from("farmers").select("*").eq("org_id", ctx.org.id),
    supabase.from("estimates").select("farm_id, created_at").eq("org_id", ctx.org.id).order("created_at", { ascending: false }).limit(10000),
  ]);
  if (!project) return { error: "Project not found." };
  if (!farms?.length) return { error: "This project has no enrolled farms." };
  const lastRun = new Map<string, string>();
  for (const e of latest ?? []) if (!lastRun.has(e.farm_id)) lastRun.set(e.farm_id, e.created_at);
  const queue = [...farms]
    .sort((a, b) => (lastRun.get(a.id) ?? "").localeCompare(lastRun.get(b.id) ?? ""))
    .slice(0, PROJECT_BATCH);
  const farmerById = new Map((farmers ?? []).map((f) => [f.id, f]));

  const failures: string[] = [];
  let done = 0;
  for (let i = 0; i < queue.length; i += 4) {
    const results = await Promise.all(
      queue.slice(i, i + 4).map((f) =>
        estimateOne(supabase, ctx.org.id, ctx.user.id, f, project, farmerById.get(f.farmer_id ?? "") ?? null),
      ),
    );
    results.forEach((problem, k) => (problem ? failures.push(`${queue[i + k].name}: ${problem}`) : done++));
  }
  revalidatePath(`/app/projects/${project_id}`);
  revalidatePath("/app");
  const remaining = farms.length - queue.length;
  return {
    message:
      `Estimated ${done} of ${queue.length} farms.` +
      (remaining > 0 ? ` ${remaining} more waiting; run again to continue.` : ""),
    ...(failures.length ? { error: failures.slice(0, 8).join("; ") + (failures.length > 8 ? "…" : "") } : {}),
  };
}
