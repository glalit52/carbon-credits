"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import type { Pathway } from "@/lib/database.types";
import { getOrgContext } from "@/lib/data";
import { can } from "@/lib/roles";
import { supabaseServer } from "@/lib/supabase/server";

import { type ActionResult, explain, num, refuseInDemo, str } from "./result";

const METHODOLOGY: Record<Pathway, string> = {
  rice: "VM0051",
  agroforestry: "VM0047",
  soil: "VM0042",
  other: "",
};

export async function createProject(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.manage(ctx.role)) return { error: "Your role cannot create projects." };
  const name = str(form, "name");
  const pathway = str(form, "pathway") as Pathway | null;
  if (!name) return { error: "Give the project a name." };
  if (!pathway || !(pathway in METHODOLOGY)) return { error: "Pick a pathway." };
  const methodology = str(form, "methodology") ?? METHODOLOGY[pathway];
  if (!methodology) return { error: "Name the methodology." };
  const supabase = await supabaseServer();
  const { data, error } = await supabase
    .from("projects")
    .insert({
      org_id: ctx.org.id,
      name,
      pathway,
      methodology,
      registry: str(form, "registry"),
      country: str(form, "country"),
      region: str(form, "region"),
      start_date: str(form, "start_date"),
      crediting_period_yrs: num(form, "crediting_period_yrs"),
      created_by: ctx.user.id,
    })
    .select("id")
    .single();
  if (error) return { error: explain(error.message) };
  revalidatePath("/app/projects");
  redirect(`/app/projects/${data.id}`);
}

export async function createFarmer(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.enrol(ctx.role)) return { error: "Your role cannot enrol farmers." };
  const name = str(form, "name");
  if (!name) return { error: "Name is required." };
  const supabase = await supabaseServer();
  const { data, error } = await supabase
    .from("farmers")
    .insert({
      org_id: ctx.org.id,
      name,
      phone: str(form, "phone"),
      village: str(form, "village"),
      district: str(form, "district"),
      state: str(form, "state"),
      country: str(form, "country"),
      external_ref: str(form, "external_ref"),
      consent_on: str(form, "consent_on"),
      consent_reference: str(form, "consent_reference"),
      carbon_rights_ref: str(form, "carbon_rights_ref"),
      carbon_rights_signed_on: str(form, "carbon_rights_signed_on"),
      payout_method: str(form, "payout_method") as "bank" | "upi" | "mobile_money" | "cash" | "other" | null,
      payout_reference: str(form, "payout_reference"),
      created_by: ctx.user.id,
    })
    .select("id")
    .single();
  if (error) return { error: explain(error.message) };
  revalidatePath("/app/farmers");
  redirect(`/app/farmers/${data.id}`);
}
