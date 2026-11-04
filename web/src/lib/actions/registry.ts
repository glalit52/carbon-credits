"use server";

import { revalidatePath } from "next/cache";

import { getOrgContext, listProjects, listVintages } from "@/lib/data";
import { DEMO } from "@/lib/env";
import { EngineError, type Reconciliation, runReconcile } from "@/lib/engine";
import { can } from "@/lib/roles";
import { supabaseServer } from "@/lib/supabase/server";

import { type ActionResult, explain, refuseInDemo, str } from "./result";

/** Record the id the registry gave an issued vintage. */
export async function setRegistryReference(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const id = str(form, "vintage_id");
  const ref = str(form, "registry_ref");
  if (!id || !ref) return { error: "Give the reference the registry shows." };
  const supabase = await supabaseServer();
  const { error } = await supabase.rpc("set_registry_reference", { vintage: id, ref });
  if (error) return { error: explain(error.message) };
  revalidatePath(`/app/credits/${id}`);
  return { message: "Registry reference recorded." };
}

export type ReconcileState = { error?: string; result?: Reconciliation; labels?: Record<string, string> };

/**
 * Our issued vintages against a registry's CSV export. Reads only: nothing is
 * changed on either side, the result says where the two disagree.
 */
export async function reconcileRegistry(_: ReconcileState, form: FormData): Promise<ReconcileState> {
  const ctx = await getOrgContext();
  if (!can.manage(ctx.role) && !can.administer(ctx.role)) {
    return { error: "Your role in this organisation does not allow that." };
  }
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose the registry's CSV export." };
  if (file.size > 3_500_000) return { error: "Registry exports must be under 3.5 MB; filter it to this project." };
  const registry = str(form, "registry") ?? "Verra";
  const projectId = str(form, "project_id");

  const [vintages, projects] = await Promise.all([listVintages(ctx.org.id, projectId ?? undefined), listProjects(ctx.org.id)]);
  const name = new Map(projects.map((p) => [p.id, p.name]));
  const issued = vintages.filter((v) => v.status === "issued");
  if (!issued.length) return { error: "No issued vintages to reconcile yet." };
  try {
    const result = await runReconcile({
      registry,
      csv: await file.text(),
      issuances: issued.map((v) => ({
        id: v.id,
        year: v.year,
        quantity: v.issuable,
        registry_ref: v.registry_ref,
      })),
    });
    return {
      result,
      labels: Object.fromEntries(issued.map((v) => [v.id, `${name.get(v.project_id) ?? "Project"} ${v.year}`])),
    };
  } catch (e) {
    if (e instanceof EngineError && DEMO) {
      return { error: "Reconciliation runs in the engine; the demo has no engine connected. " + e.message };
    }
    return { error: e instanceof EngineError ? e.message : (e as Error).message };
  }
}
