"use server";

import { revalidatePath } from "next/cache";

import type { Json } from "@/lib/database.types";
import { getOrgContext } from "@/lib/data";
import { parseBoundaryFile } from "@/lib/geo";
import {
  type FarmDraft,
  type ImportKind,
  type ImportPreview,
  previewFarmFeatures,
  previewFarms,
  previewPractices,
  previewSoil,
} from "@/lib/import";
import { can } from "@/lib/roles";
import { supabaseServer } from "@/lib/supabase/server";

import { type ActionResult, explain, refuseInDemo } from "./result";

const MAX_ROWS = 5000;
const CHUNK = 500;

/** The same parse the browser previewed, run again where it can be trusted. */
function reparse(kind: ImportKind, text: string, filename: string): ImportPreview<unknown> {
  if (kind === "farms") {
    const lower = filename.toLowerCase();
    if (/\.(kml|geojson|json|wkt)$/.test(lower) || /^\s*[{<]/.test(text)) {
      return previewFarmFeatures(parseBoundaryFile(text, filename));
    }
    return previewFarms(text);
  }
  return kind === "practices" ? previewPractices(text) : previewSoil(text);
}

function chunks<T>(rows: T[]): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < rows.length; i += CHUNK) out.push(rows.slice(i, i + CHUNK));
  return out;
}

export async function commitImport(input: {
  kind: ImportKind;
  text: string;
  filename: string;
  projectId?: string | null;
}): Promise<ActionResult & { imported?: number; skipped?: number }> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.enrol(ctx.role)) return { error: "Your role cannot import data." };

  let preview: ImportPreview<unknown>;
  try {
    preview = reparse(input.kind, input.text, input.filename);
  } catch (e) {
    return { error: `Could not read the file: ${(e as Error).message}` };
  }
  if (preview.results.length > MAX_ROWS) {
    return { error: `That is ${preview.results.length} rows; import at most ${MAX_ROWS} at a time.` };
  }
  const good = preview.results.filter((r) => r.value);
  if (!good.length) return { error: "No row passed validation, so nothing was imported." };

  const supabase = await supabaseServer();
  let imported = 0;

  if (input.kind === "farms") {
    // Farmers first: reuse by reference, else by exact name, else create.
    const { data: existing } = await supabase.from("farmers").select("id, name, external_ref").eq("org_id", ctx.org.id);
    const byRef = new Map((existing ?? []).filter((f) => f.external_ref).map((f) => [f.external_ref!, f.id]));
    const byName = new Map((existing ?? []).map((f) => [f.name.toLowerCase(), f.id]));
    const drafts = good.map((r) => r.value as FarmDraft);
    const toCreate = new Map<string, NonNullable<FarmDraft["farmer"]>>();
    for (const d of drafts) {
      if (!d.farmer) continue;
      const key = d.farmer.external_ref ?? d.farmer.name.toLowerCase();
      if (!byRef.has(d.farmer.external_ref ?? "") && !byName.has(d.farmer.name.toLowerCase())) toCreate.set(key, d.farmer);
    }
    for (const batch of chunks([...toCreate.values()])) {
      const { data, error } = await supabase
        .from("farmers")
        .insert(batch.map((f) => ({ ...f, org_id: ctx.org.id, created_by: ctx.user.id })))
        .select("id, name, external_ref");
      if (error) return { error: `Creating farmers failed: ${explain(error.message)}` };
      for (const f of data) {
        if (f.external_ref) byRef.set(f.external_ref, f.id);
        byName.set(f.name.toLowerCase(), f.id);
      }
    }
    const rows = drafts.map((d) => {
      const { farmer, ...farm } = d;
      return {
        ...farm,
        org_id: ctx.org.id,
        project_id: input.projectId || null,
        farmer_id: farmer
          ? (farmer.external_ref && byRef.get(farmer.external_ref)) || byName.get(farmer.name.toLowerCase()) || null
          : null,
        source: "imported" as const,
        created_by: ctx.user.id,
      };
    });
    for (const batch of chunks(rows)) {
      const { error } = await supabase.from("farms").insert(batch);
      if (error) {
        return { error: `Stopped after ${imported} farms: ${explain(error.message)}`, imported };
      }
      imported += batch.length;
    }
  } else {
    // Practices and soil attach to farms by the customer's own reference.
    const { data: farms } = await supabase.from("farms").select("id, external_ref").eq("org_id", ctx.org.id);
    const farmByRef = new Map((farms ?? []).filter((f) => f.external_ref).map((f) => [f.external_ref!, f.id]));
    const unmatched: number[] = [];
    const rows = good.flatMap((r) => {
      const v = r.value as { farm_ref: string } & Record<string, unknown>;
      const farm_id = farmByRef.get(v.farm_ref);
      if (!farm_id) {
        unmatched.push(r.row);
        return [];
      }
      const rest = Object.fromEntries(Object.entries(v).filter(([k]) => k !== "farm_ref"));
      return [{ ...rest, farm_id, org_id: ctx.org.id, recorded_by: ctx.user.id }];
    });
    if (!rows.length) return { error: "None of the farm_ref values match a farm in this organisation." };
    const table = input.kind === "practices" ? "practice_records" : "soil_samples";
    for (const batch of chunks(rows)) {
      // The two tables have different columns; each row was built for its own.
      const { error } = await supabase.from(table).insert(batch as never);
      if (error) return { error: `Stopped after ${imported} rows: ${explain(error.message)}`, imported };
      imported += batch.length;
    }
    if (unmatched.length) {
      preview.results
        .filter((r) => unmatched.includes(r.row))
        .forEach((r) => r.errors.push("farm_ref matches no farm"));
    }
  }

  const errors = preview.results
    .filter((r) => r.errors.length)
    .slice(0, 500)
    .map((r) => ({ row: r.row, errors: r.errors }));
  await supabase.from("imports").insert({
    org_id: ctx.org.id,
    kind: input.kind,
    filename: input.filename,
    row_count: preview.results.length,
    ok_count: imported,
    error_count: preview.results.length - imported,
    errors: errors as unknown as Json,
    created_by: ctx.user.id,
  });
  revalidatePath("/app", "layout");
  return {
    message: `Imported ${imported} of ${preview.results.length} rows.`,
    imported,
    skipped: preview.results.length - imported,
  };
}
