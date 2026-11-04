"use server";

import { revalidatePath } from "next/cache";

import { getOrgContext } from "@/lib/data";
import { isLanguage } from "@/lib/i18n";
import { can } from "@/lib/roles";
import { supabaseServer } from "@/lib/supabase/server";

import { type ActionResult, explain, num, refuseInDemo, str } from "./result";

/** A link the farmer can open without an account. Expires; can be revoked. */
export async function createStatementLink(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.enrol(ctx.role)) return { error: "Your role cannot share statements." };
  const farmer_id = str(form, "farmer_id");
  const language = str(form, "language");
  const days = Math.min(Math.max(num(form, "days") ?? 90, 1), 365);
  if (!farmer_id || !isLanguage(language)) return { error: "Pick a language." };
  const supabase = await supabaseServer();
  const { error } = await supabase.from("statement_links").insert({
    org_id: ctx.org.id,
    farmer_id,
    language,
    expires_at: new Date(Date.now() + days * 86_400_000).toISOString(),
    created_by: ctx.user.id,
  });
  if (error) return { error: explain(error.message) };
  revalidatePath(`/app/farmers/${farmer_id}`);
  return { message: "Link created." };
}

export async function revokeStatementLink(form: FormData): Promise<void> {
  if (refuseInDemo()) return;
  const id = str(form, "id");
  const farmer_id = str(form, "farmer_id");
  if (!id) return;
  const ctx = await getOrgContext();
  const supabase = await supabaseServer();
  await supabase.from("statement_links").update({ revoked_at: new Date().toISOString() }).eq("id", id).eq("org_id", ctx.org.id);
  revalidatePath(`/app/farmers/${farmer_id}`);
}
