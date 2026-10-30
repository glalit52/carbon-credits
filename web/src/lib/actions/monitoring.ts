"use server";

import { revalidatePath } from "next/cache";

import type { Json } from "@/lib/database.types";
import { getFarm, getOrgContext, listEstimates } from "@/lib/data";
import { EngineError, type EngineResult, runSensors } from "@/lib/engine";
import { can } from "@/lib/roles";
import { supabaseServer } from "@/lib/supabase/server";

import { type ActionResult, explain, refuseInDemo, str } from "./result";

const MAX_LOGGER_BYTES = 3_500_000;

/**
 * A water-level logger file for one farm. The engine cleans it (gaps,
 * flatlines, spikes) and scores the farm's radar calls against it; the file
 * goes to the evidence bucket and the engine's summary is kept with it.
 */
export async function uploadLogger(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.enrol(ctx.role)) return { error: "Your role in this organisation does not allow that." };
  const farmId = str(form, "farm_id");
  const file = form.get("file");
  if (!farmId || !(file instanceof File) || file.size === 0) return { error: "Choose a logger file." };
  if (file.size > MAX_LOGGER_BYTES) {
    return { error: "Logger files must be under 3.5 MB; split a long record by season." };
  }
  const farm = await getFarm(ctx.org.id, farmId);
  if (!farm) return { error: "Farm not found." };

  const latest = (await listEstimates(ctx.org.id, farm.id))
    .map((e) => (e.result as unknown as EngineResult).monitoring)
    .filter(Boolean)
    .at(-1);

  const csv = await file.text();
  let summary;
  try {
    summary = await runSensors({ csv, plot_id: farm.external_ref ?? farm.id, radar: latest?.radar ?? [] });
  } catch (e) {
    return { error: e instanceof EngineError ? e.message : `Could not read the file: ${(e as Error).message}` };
  }
  const days = summary.days.map((d) => d.day).sort();

  const supabase = await supabaseServer();
  const safe = file.name.replace(/[^\w.-]+/g, "_").slice(-80);
  const path = `${ctx.org.id}/farms/${farm.id}/loggers/${Date.now()}-${safe}`;
  const { error: upErr } = await supabase.storage.from("evidence").upload(path, file, { contentType: "text/csv" });
  if (upErr) return { error: `Upload failed: ${explain(upErr.message)}` };

  const { error } = await supabase.from("sensor_uploads").insert({
    org_id: ctx.org.id,
    farm_id: farm.id,
    file_name: file.name.slice(0, 200),
    file_path: path,
    readings: summary.readings,
    first_day: days[0] ?? null,
    last_day: days.at(-1) ?? null,
    summary: summary as unknown as Json,
    uploaded_by: ctx.user.id,
  });
  if (error) return { error: explain(error.message) };
  revalidatePath(`/app/farms/${farm.id}/monitoring`);
  const devices = summary.records.length;
  const events = summary.records.reduce((n, r) => n + r.dry_downs.length, 0);
  return {
    message: `${summary.readings.toLocaleString()} readings from ${devices} logger${devices === 1 ? "" : "s"}; ${events} measured dry-down${events === 1 ? "" : "s"}.`,
  };
}
