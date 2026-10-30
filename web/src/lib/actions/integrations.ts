"use server";

import { revalidatePath } from "next/cache";

import { getOrgContext } from "@/lib/data";
import { can } from "@/lib/roles";
import { supabaseServer } from "@/lib/supabase/server";

import { refuseInDemo, str } from "./result";

export async function toggleIntegration(form: FormData): Promise<void> {
  if (refuseInDemo()) return;
  const ctx = await getOrgContext();
  if (!can.administer(ctx.role)) return;
  const provider = str(form, "provider");
  if (!provider) return;
  const enabled = str(form, "enabled") === "true";
  const supabase = await supabaseServer();
  await supabase
    .from("integrations")
    .upsert({ org_id: ctx.org.id, provider, enabled }, { onConflict: "org_id,provider" });
  revalidatePath("/app/integrations");
}
