"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import type { Json, PaymentStatus, VintageStatus } from "@/lib/database.types";
import { getOrgContext, listEstimates } from "@/lib/data";
import { can } from "@/lib/roles";
import { supabaseServer } from "@/lib/supabase/server";

import { type ActionResult, explain, num, refuseInDemo, str } from "./result";

/**
 * Build (or rebuild) a project's draft vintage for a year from its farms'
 * latest estimates. Only enrolled farms count; whole credits are the floor of
 * the net, the remainder is carried, never rounded up.
 */
export async function buildVintage(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.manage(ctx.role)) return { error: "Your role cannot prepare vintages." };
  const project_id = str(form, "project_id");
  const year = num(form, "year");
  if (!project_id || !year) return { error: "Pick a project and a year." };

  const supabase = await supabaseServer();
  const { data: farms } = await supabase
    .from("farms")
    .select("id, name, status")
    .eq("org_id", ctx.org.id)
    .eq("project_id", project_id);
  const enrolled = new Map((farms ?? []).filter((f) => f.status === "enrolled").map((f) => [f.id, f.name]));
  const estimates = (await listEstimates(ctx.org.id)).filter((e) => e.year === year && enrolled.has(e.farm_id));
  if (!estimates.length) {
    return { error: `No estimates for ${year} on this project's enrolled farms. Run estimates on the farms first.` };
  }
  const gross = estimates.reduce((s, e) => s + Number(e.gross_t), 0);
  const net = estimates.reduce((s, e) => s + Number(e.net_t), 0);
  const derivation = {
    method: "sum of each enrolled farm's latest estimate; whole credits floor the net",
    built_at: new Date().toISOString(),
    farms: estimates.map((e) => ({
      farm_id: e.farm_id,
      farm: enrolled.get(e.farm_id),
      estimate_id: e.id,
      gross_t: Number(e.gross_t),
      net_t: Number(e.net_t),
      data_quality: e.data_quality,
    })),
    excluded: [...(farms ?? [])].filter((f) => f.status !== "enrolled").map((f) => ({ farm_id: f.id, status: f.status })),
  };
  const row = {
    org_id: ctx.org.id,
    project_id,
    year,
    gross_t: Math.round(gross * 1e4) / 1e4,
    net_t: Math.round(net * 1e4) / 1e4,
    issuable: Math.max(0, Math.floor(net)),
    derivation: derivation as unknown as Json,
  };

  const { data: existing } = await supabase
    .from("vintages")
    .select("id, status")
    .eq("project_id", project_id)
    .eq("year", year)
    .maybeSingle();
  if (existing && existing.status !== "draft") {
    return { error: `The ${year} vintage is already ${existing.status}; it can no longer be rebuilt.` };
  }
  const { data, error } = existing
    ? await supabase.from("vintages").update(row).eq("id", existing.id).select("id").single()
    : await supabase.from("vintages").insert(row).select("id").single();
  if (error) return { error: explain(error.message) };
  revalidatePath("/app/credits");
  redirect(`/app/credits/${data.id}`);
}

export async function transitionVintage(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const id = str(form, "id");
  const to = str(form, "to") as VintageStatus | null;
  if (!id || !to) return { error: "Missing vintage or target state." };
  const supabase = await supabaseServer();
  const { error } = await supabase.rpc("transition_vintage", {
    vintage: id,
    to_state: to,
    review_note: str(form, "note"),
  });
  if (error) return { error: explain(error.message) };
  revalidatePath(`/app/credits/${id}`);
  revalidatePath("/app/credits");
  return { message: "Done." };
}

/**
 * Split an issued vintage between farmers by each farm's share of the net,
 * at a price and farmer share the organisation chooses.
 */
export async function raisePayments(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.administer(ctx.role)) return { error: "Only owners and admins raise payments." };
  const id = str(form, "vintage_id");
  const price = num(form, "price");
  const share = num(form, "share");
  const currency = (str(form, "currency") ?? "USD").toUpperCase();
  if (!id || price === null || share === null) return { error: "Price and farmer share are required." };
  if (price <= 0 || share <= 0 || share > 100) return { error: "Price must be positive and the share between 0 and 100 %." };

  const supabase = await supabaseServer();
  const { data: v } = await supabase.from("vintages").select("*").eq("id", id).eq("org_id", ctx.org.id).single();
  if (!v) return { error: "Vintage not found." };
  if (v.status !== "issued") return { error: "Payments are raised against issued credits, not expected ones." };
  const farms = ((v.derivation as { farms?: { farm_id: string; net_t: number }[] })?.farms ?? []).filter((f) => f.net_t > 0);
  const { data: farmRows } = await supabase.from("farms").select("id, farmer_id").in("id", farms.map((f) => f.farm_id));
  const farmerOf = new Map((farmRows ?? []).map((f) => [f.id, f.farmer_id]));
  const total = farms.reduce((s, f) => s + f.net_t, 0);
  const byFarmer = new Map<string, number>();
  const unpaid: string[] = [];
  for (const f of farms) {
    const farmer = farmerOf.get(f.farm_id);
    if (!farmer) {
      unpaid.push(f.farm_id);
      continue;
    }
    byFarmer.set(farmer, (byFarmer.get(farmer) ?? 0) + (v.issuable * f.net_t) / total);
  }
  if (!byFarmer.size) return { error: "No farm in this vintage has a farmer linked to pay." };
  const due = new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10);
  const rows = [...byFarmer].map(([farmer_id, credits]) => ({
    org_id: ctx.org.id,
    vintage_id: id,
    farmer_id,
    credits: Math.round(credits * 1e4) / 1e4,
    amount: Math.round(credits * price * (share / 100) * 100) / 100,
    currency,
    due_on: due,
  }));
  const { error } = await supabase.from("payments").insert(rows);
  if (error) return { error: explain(error.message) };
  revalidatePath(`/app/credits/${id}`);
  revalidatePath("/app/payments");
  return {
    message:
      `Raised ${rows.length} payments.` +
      (unpaid.length ? ` ${unpaid.length} farm(s) have no farmer linked and were left out.` : ""),
  };
}

export async function setPaymentStatus(form: FormData): Promise<void> {
  if (refuseInDemo()) return;
  const ctx = await getOrgContext();
  if (!can.administer(ctx.role)) return;
  const id = str(form, "id");
  const status = str(form, "status") as PaymentStatus | null;
  if (!id || !status) return;
  const supabase = await supabaseServer();
  await supabase
    .from("payments")
    .update({
      status,
      paid_on: status === "paid" ? new Date().toISOString().slice(0, 10) : null,
      reference: str(form, "reference"),
    })
    .eq("id", id)
    .eq("org_id", ctx.org.id);
  revalidatePath("/app/payments");
}
