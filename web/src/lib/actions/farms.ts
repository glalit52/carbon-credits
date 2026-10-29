"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import type {
  Database,
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

export async function createFarm(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.enrol(ctx.role)) return { error: "Your role cannot enrol farms." };

  const name = str(form, "name");
  if (!name) return { error: "Give the farm a name." };
  const { geometry, error } = geometryFrom(form);
  if (!geometry) return { error };
  const { seasons, error: seasonError } = seasonsFrom(form);
  if (seasonError) return { error: seasonError };
  const tenure = str(form, "tenure") as Tenure | null;
  if (tenure && !TENURES.includes(tenure)) return { error: "Unknown tenure basis." };

  const supabase = await supabaseServer();

  let farmerId = str(form, "farmer_id");
  const newFarmer = str(form, "new_farmer_name");
  if (farmerId === "new") {
    if (!newFarmer) return { error: "Name the new farmer, or pick an existing one." };
    const { data, error: e } = await supabase
      .from("farmers")
      .insert({
        org_id: ctx.org.id,
        name: newFarmer,
        phone: str(form, "new_farmer_phone"),
        village: str(form, "new_farmer_village"),
        consent_on: str(form, "consent_on"),
        consent_reference: str(form, "consent_reference"),
        created_by: ctx.user.id,
      })
      .select("id")
      .single();
    if (e) return { error: explain(e.message) };
    farmerId = data.id;
  }

  const species = str(form, "species")
    ?.split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const { data, error: insertError } = await supabase
    .from("farms")
    .insert({
      org_id: ctx.org.id,
      project_id: str(form, "project_id"),
      farmer_id: farmerId,
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

/** Run the engine for one farm and keep one estimate row per year. */
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

  try {
    const request = estimateRequest(farm, farmer, project.pathway);
    const result = await runEstimate(request);
    const rows = result.vintages
      .filter((v) => v.net_t !== undefined)
      .map((v) => ({
        org_id: ctx.org.id,
        farm_id,
        year: v.year,
        methodology: result.methodology,
        gross_t: v.gross_t ?? 0,
        net_t: v.net_t ?? 0,
        data_quality: result.data_quality,
        input: request as unknown as Json,
        result: { ...result, vintages: [v] } as unknown as Json,
        engine_version: "carbonstack@estimate-v1",
        requested_by: ctx.user.id,
      }));
    if (!rows.length) return { error: "No year could be estimated yet: no season has closed since enrolment." };
    const { error } = await supabase.from("estimates").insert(rows);
    if (error) return { error: explain(error.message) };
  } catch (e) {
    return { error: e instanceof EngineError ? e.message : `Estimate failed: ${(e as Error).message}` };
  }
  revalidatePath(`/app/farms/${farm_id}`);
  revalidatePath("/app");
  return { message: "Estimate updated." };
}

export async function evidenceUrl(path: string): Promise<string | null> {
  if (refuseInDemo()) return null;
  const supabase = await supabaseServer();
  const { data } = await supabase.storage.from("evidence").createSignedUrl(path, 300);
  return data?.signedUrl ?? null;
}
