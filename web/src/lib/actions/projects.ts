"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import type { Pathway } from "@/lib/database.types";
import { getOrgContext, isDemoOrg } from "@/lib/data";
import { demo } from "@/lib/demo";
import { isLanguage } from "@/lib/i18n";
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
  const ctx = await getOrgContext();
  if (!can.manage(ctx.role)) return { error: "Your role cannot create projects." };
  const name = str(form, "name");
  const pathway = str(form, "pathway") as Pathway | null;
  if (!name) return { error: "Give the project a name." };
  if (!pathway || !(pathway in METHODOLOGY)) return { error: "Pick a pathway." };
  const methodology = str(form, "methodology") ?? METHODOLOGY[pathway];
  if (!methodology) return { error: "Name the methodology." };

  if (ctx.demo) {
    const projId = crypto.randomUUID();
    demo.projects.unshift({
      id: projId,
      org_id: ctx.org.id,
      name,
      pathway,
      methodology,
      registry: str(form, "registry") || "Verra",
      country: str(form, "country") || "India",
      region: str(form, "region") || "Punjab",
      start_date: str(form, "start_date") || new Date().toISOString().slice(0, 10),
      crediting_period_yrs: num(form, "crediting_period_yrs") || 20,
      status: "design",
      created_at: new Date().toISOString(),
      created_by: ctx.user.id,
    });
    revalidatePath("/app");
    revalidatePath("/app/projects");
    redirect(`/app/projects/${projId}`);
  }

  const refused = refuseInDemo();
  if (refused) return refused;
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

function farmerFields(form: FormData, name: string) {
  return {
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
    language: (() => {
      const l = str(form, "language");
      return isLanguage(l) ? l : "en";
    })(),
  };
}

export async function createFarmer(_: ActionResult, form: FormData): Promise<ActionResult> {
  const ctx = await getOrgContext();
  if (!can.enrol(ctx.role)) return { error: "Your role cannot enrol farmers." };
  const name = str(form, "name");
  if (!name) return { error: "Name is required." };

  if (ctx.demo) {
    const farmerId = crypto.randomUUID();
    demo.farmers.unshift({
      ...farmerFields(form, name),
      id: farmerId,
      org_id: ctx.org.id,
      created_at: new Date().toISOString(),
      created_by: ctx.user.id,
    });
    revalidatePath("/app/farmers");
    redirect(`/app/farmers/${farmerId}`);
  }

  const refused = refuseInDemo();
  if (refused) return refused;
  const supabase = await supabaseServer();
  const { data, error } = await supabase
    .from("farmers")
    .insert({ ...farmerFields(form, name), org_id: ctx.org.id, created_by: ctx.user.id })
    .select("id")
    .single();
  if (error) return { error: explain(error.message) };
  revalidatePath("/app/farmers");
  redirect(`/app/farmers/${data.id}`);
}

export async function updateFarmer(_: ActionResult, form: FormData): Promise<ActionResult> {
  const ctx = await getOrgContext();
  if (!can.enrol(ctx.role)) return { error: "Your role cannot edit farmers." };
  const id = str(form, "id");
  const name = str(form, "name");
  if (!id || !name) return { error: "Name is required." };

  if (ctx.demo) {
    const existing = demo.farmers.find((f) => f.id === id);
    if (existing) {
      Object.assign(existing, farmerFields(form, name));
    }
    revalidatePath(`/app/farmers/${id}`);
    redirect(`/app/farmers/${id}`);
  }

  const refused = refuseInDemo();
  if (refused) return refused;
  const supabase = await supabaseServer();
  const { error } = await supabase
    .from("farmers")
    .update(farmerFields(form, name))
    .eq("id", id)
    .eq("org_id", ctx.org.id);
  if (error) return { error: explain(error.message) };
  revalidatePath(`/app/farmers/${id}`);
  redirect(`/app/farmers/${id}`);
}

const STATUSES = ["design", "listed", "registered", "closed"] as const;

export async function updateProject(_: ActionResult, form: FormData): Promise<ActionResult> {
  const ctx = await getOrgContext();
  if (!can.manage(ctx.role)) return { error: "Your role cannot edit projects." };
  const id = str(form, "id");
  const name = str(form, "name");
  if (!id || !name) return { error: "Name is required." };
  const status = str(form, "status") as (typeof STATUSES)[number] | null;
  if (status && !STATUSES.includes(status)) return { error: "Unknown status." };

  if (ctx.demo || isDemoOrg(ctx.org.id) || ctx.user.id.startsWith("mock-")) {
    const p = demo.projects.find((x) => x.id === id);
    if (p) {
      p.name = name;
      if (str(form, "registry")) p.registry = str(form, "registry");
      if (str(form, "country")) p.country = str(form, "country");
      if (str(form, "region")) p.region = str(form, "region");
      if (str(form, "start_date")) p.start_date = str(form, "start_date");
      if (num(form, "crediting_period_yrs")) p.crediting_period_yrs = num(form, "crediting_period_yrs")!;
      if (status) p.status = status;
    }
    revalidatePath("/app/projects");
    revalidatePath(`/app/projects/${id}`);
    redirect(`/app/projects/${id}`);
  }

  const refused = refuseInDemo();
  if (refused) return refused;
  // Pathway and methodology stay as created: estimates already made under
  // them would silently stop matching the project they belong to.
  const supabase = await supabaseServer();
  const { error } = await supabase
    .from("projects")
    .update({
      name,
      registry: str(form, "registry"),
      country: str(form, "country"),
      region: str(form, "region"),
      start_date: str(form, "start_date"),
      crediting_period_yrs: num(form, "crediting_period_yrs"),
      ...(status ? { status } : {}),
    })
    .eq("id", id)
    .eq("org_id", ctx.org.id);
  if (error) return { error: explain(error.message) };
  revalidatePath(`/app/projects/${id}`);
  redirect(`/app/projects/${id}`);
}
