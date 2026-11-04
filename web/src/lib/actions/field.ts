"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";

import type { Language, PolygonGeometry, Season } from "@/lib/database.types";
import { getOrgContext } from "@/lib/data";
import type { FieldDraft } from "@/lib/field-queue";
import { measure, validate } from "@/lib/geo";
import { FIELD_LANG_COOKIE, isLanguage } from "@/lib/i18n";
import { can } from "@/lib/roles";
import { supabaseServer } from "@/lib/supabase/server";

import { explain, refuseInDemo } from "./result";

export async function setFieldLanguage(lang: Language): Promise<void> {
  if (!isLanguage(lang)) return;
  (await cookies()).set(FIELD_LANG_COOKIE, lang, { path: "/", maxAge: 365 * 86_400, sameSite: "lax" });
}

export type SyncResult = { ok: true; farm_id: string; duplicate?: boolean } | { ok: false; error: string; retry: boolean };

const TENURES = ["owned_title", "registered_lease", "community_right", "grama_sabha_consent", "undocumented"];
const ECOSYSTEMS = ["irrigated_lowland", "rainfed", "upland", "deepwater", "unknown"];
const CONTROL = ["full", "irrigation_only", "none", "unknown"];
const MAX_PHOTO = 12 * 1024 * 1024;

/**
 * One field enrolment, sent from the phone's queue. Safe to send twice: the
 * draft id becomes the farm's (and a new farmer's) reference, which the
 * database keeps unique, so a resend after a lost reply finds the first one.
 */
export async function submitFieldEnrolment(form: FormData): Promise<SyncResult> {
  const refused = refuseInDemo();
  if (refused) return { ok: false, error: refused.error ?? "demo", retry: false };
  const ctx = await getOrgContext();
  if (!can.enrol(ctx.role)) return { ok: false, error: "Your role cannot enrol farms.", retry: false };

  let d: Omit<FieldDraft, "consent_photo" | "tenure_photo">;
  try {
    d = JSON.parse(String(form.get("draft")));
  } catch {
    return { ok: false, error: "The enrolment on this phone could not be read.", retry: false };
  }
  if (!/^[0-9a-f-]{36}$/i.test(d.id ?? "")) return { ok: false, error: "Malformed enrolment id.", retry: false };
  const ref = `FLD-${d.id.replace(/-/g, "").slice(0, 12).toUpperCase()}`;

  const supabase = await supabaseServer();
  const { data: existing } = await supabase
    .from("farms")
    .select("id")
    .eq("org_id", ctx.org.id)
    .eq("external_ref", ref)
    .maybeSingle();
  if (existing) return { ok: true, farm_id: existing.id, duplicate: true };

  // The same checks the back office makes.
  const boundary = d.boundary as PolygonGeometry;
  const problems = boundary?.type === "Polygon" ? validate(boundary) : ["the boundary must be a polygon"];
  if (problems.length) return { ok: false, error: `Boundary: ${problems.join("; ")}`, retry: false };
  const f = d.farm;
  if (!f?.name?.trim()) return { ok: false, error: "The field needs a name.", retry: false };
  if (!TENURES.includes(f.tenure)) return { ok: false, error: "Unknown tenure basis.", retry: false };
  if (f.rice_ecosystem && !ECOSYSTEMS.includes(f.rice_ecosystem)) return { ok: false, error: "Unknown water source.", retry: false };
  if (f.water_control && !CONTROL.includes(f.water_control)) return { ok: false, error: "Unknown drainage answer.", retry: false };
  for (const key of ["consent_photo", "tenure_photo"]) {
    const file = form.get(key);
    if (file instanceof File && file.size > MAX_PHOTO) return { ok: false, error: "A photo is over 12 MB.", retry: false };
  }

  const upload = async (key: string, folder: string): Promise<string | null> => {
    const file = form.get(key);
    if (!(file instanceof File) || file.size === 0) return null;
    const path = `${ctx.org.id}/${folder}/${ref}-${key}.jpg`;
    const { error } = await supabase.storage.from("evidence").upload(path, file, {
      contentType: file.type || "image/jpeg",
      upsert: true,
    });
    if (error) throw new Error(`Photo upload failed: ${explain(error.message)}`);
    return path;
  };

  try {
    // -- farmer ----------------------------------------------------------------
    let farmerId: string;
    if (d.farmer.mode === "existing") {
      farmerId = d.farmer.id;
    } else {
      const fr = d.farmer;
      if (!fr.name?.trim()) return { ok: false, error: "The farmer needs a name.", retry: false };
      const { data: again } = await supabase
        .from("farmers")
        .select("id")
        .eq("org_id", ctx.org.id)
        .eq("external_ref", ref)
        .maybeSingle();
      if (again) {
        farmerId = again.id;
      } else {
        const consentPath = await upload("consent_photo", `farmers/${ref}`);
        const today = d.created_at.slice(0, 10);
        const { data, error } = await supabase
          .from("farmers")
          .insert({
            org_id: ctx.org.id,
            name: fr.name.trim(),
            phone: fr.phone?.trim() || null,
            village: fr.village?.trim() || null,
            language: isLanguage(fr.language) ? fr.language : "en",
            external_ref: ref,
            consent_on: fr.consent ? today : null,
            consent_reference: fr.consent ? (consentPath ?? "recorded in the field, no photo") : null,
            created_by: ctx.user.id,
          })
          .select("id")
          .single();
        if (error) return { ok: false, error: explain(error.message), retry: false };
        farmerId = data.id;
      }
    }

    // -- farm --------------------------------------------------------------------
    // A rice estimate needs the crop calendar. The phone does not ask for it:
    // farms in one project share a calendar, so take the one most of them use.
    let seasons: Season[] = [];
    if (f.project_id) {
      const { data: siblings } = await supabase
        .from("farms")
        .select("seasons")
        .eq("org_id", ctx.org.id)
        .eq("project_id", f.project_id)
        .limit(200);
      const counts = new Map<string, number>();
      for (const s of siblings ?? []) {
        const key = JSON.stringify(s.seasons ?? []);
        if (key !== "[]") counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      const common = [...counts].sort((a, b) => b[1] - a[1])[0];
      if (common) seasons = JSON.parse(common[0]);
    }

    const { data: farm, error } = await supabase
      .from("farms")
      .insert({
        org_id: ctx.org.id,
        project_id: f.project_id,
        farmer_id: farmerId,
        name: f.name.trim(),
        external_ref: ref,
        boundary,
        ...measure(boundary),
        practice: f.practice || null,
        tenure: f.tenure as FieldDraft["farm"]["tenure"],
        tenure_reference: f.tenure_reference?.trim() || null,
        rice_ecosystem: f.rice_ecosystem,
        water_control: f.water_control,
        enrolled_on: d.created_at.slice(0, 10),
        seasons,
        source: "gps",
        status: "enrolled",
        created_by: ctx.user.id,
      })
      .select("id")
      .single();
    if (error) {
      // Two sends racing: the other one won.
      if (/duplicate key/i.test(error.message)) {
        const { data: won } = await supabase.from("farms").select("id").eq("org_id", ctx.org.id).eq("external_ref", ref).single();
        if (won) return { ok: true, farm_id: won.id, duplicate: true };
      }
      return { ok: false, error: explain(error.message), retry: false };
    }

    // -- the visit itself, with its photos and GPS quality, as a field record --------
    const landPath = await upload("tenure_photo", `farms/${farm.id}`);
    const worst = Math.max(...(d.corners ?? []).map((c) => c.accuracy_m), 0);
    await supabase.from("practice_records").insert({
      org_id: ctx.org.id,
      farm_id: farm.id,
      year: Number(d.created_at.slice(0, 4)),
      practice: "enrolment visit",
      started_on: d.created_at.slice(0, 10),
      notes:
        `Boundary walked with phone GPS: ${d.corners?.length ?? 0} corners, worst accuracy ${Math.round(worst)} m.` +
        (seasons.length ? " Crop calendar taken from the project's other farms." : "") +
        (landPath ? " Land record photo attached." : ""),
      evidence_path: landPath,
      recorded_by: ctx.user.id,
    });

    revalidatePath("/field");
    revalidatePath("/app/farms");
    return { ok: true, farm_id: farm.id };
  } catch (e) {
    return { ok: false, error: (e as Error).message, retry: true };
  }
}
