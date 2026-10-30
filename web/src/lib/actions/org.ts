"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type { Role } from "@/lib/database.types";
import { ACTIVE_ORG_COOKIE, getOrgContext } from "@/lib/data";
import { siteUrl } from "@/lib/env";
import { can, INVITABLE } from "@/lib/roles";
import { supabaseServer } from "@/lib/supabase/server";

import { type ActionResult, explain, refuseInDemo, str } from "./result";

const KINDS = ["developer", "aggregator", "buyer", "verifier"] as const;

async function setActiveOrg(id: string) {
  (await cookies()).set(ACTIVE_ORG_COOKIE, id, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
  });
}

export async function createOrganization(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const name = str(form, "name");
  const kind = str(form, "kind") ?? "developer";
  if (!name || name.length < 2) return { error: "Give the organisation a name." };
  if (!KINDS.includes(kind as (typeof KINDS)[number])) return { error: "Pick what kind of organisation this is." };
  const supabase = await supabaseServer();
  const { data, error } = await supabase.rpc("create_organization", {
    org_name: name,
    org_kind: kind,
    org_country: str(form, "country"),
  });
  if (error) return { error: explain(error.message) };
  await setActiveOrg(data);
  redirect("/app");
}

export async function switchOrganization(form: FormData): Promise<void> {
  const id = str(form, "org_id");
  if (!id || refuseInDemo()) return;
  const ctx = await getOrgContext();
  if (ctx.orgs.some((o) => o.org.id === id)) await setActiveOrg(id);
  redirect("/app");
}

export async function updateOrganization(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.administer(ctx.role)) return { error: "Only owners and admins can change the organisation." };
  const name = str(form, "name");
  if (!name) return { error: "Name is required." };
  const supabase = await supabaseServer();
  const { error } = await supabase
    .from("organizations")
    .update({ name, country: str(form, "country") })
    .eq("id", ctx.org.id);
  if (error) return { error: explain(error.message) };
  revalidatePath("/app", "layout");
  return { message: "Saved." };
}

export async function inviteMember(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.administer(ctx.role)) return { error: "Only owners and admins can invite people." };
  const email = str(form, "email")?.toLowerCase();
  const role = str(form, "role") as Exclude<Role, "owner"> | null;
  if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return { error: "Enter a valid email address." };
  if (!role || !INVITABLE.includes(role)) return { error: "Pick a role." };
  const supabase = await supabaseServer();
  const { data, error } = await supabase
    .from("invitations")
    .insert({ org_id: ctx.org.id, email, role, invited_by: ctx.user.id })
    .select("token")
    .single();
  if (error) return { error: explain(error.message) };
  revalidatePath("/app/settings");
  // Sending mail needs an email provider; the link works the same pasted
  // into WhatsApp, which is how field teams usually get it anyway.
  return { message: `${siteUrl()}/invite/${data.token}` };
}

export async function revokeInvitation(form: FormData): Promise<void> {
  if (refuseInDemo()) return;
  const id = str(form, "id");
  if (!id) return;
  const ctx = await getOrgContext();
  const supabase = await supabaseServer();
  await supabase.from("invitations").delete().eq("id", id).eq("org_id", ctx.org.id);
  revalidatePath("/app/settings");
}

export async function changeRole(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  const user_id = str(form, "user_id");
  const role = str(form, "role") as Role | null;
  if (!user_id || !role) return { error: "Missing member or role." };
  if (user_id === ctx.user.id) return { error: "Ask another admin to change your own role." };
  const supabase = await supabaseServer();
  const { data, error } = await supabase
    .from("memberships")
    .update({ role })
    .eq("org_id", ctx.org.id)
    .eq("user_id", user_id)
    .select();
  if (error) return { error: explain(error.message) };
  if (!data?.length) return { error: "Your role does not allow that change." };
  revalidatePath("/app/settings");
  return { message: "Role updated." };
}

export async function removeMember(form: FormData): Promise<void> {
  if (refuseInDemo()) return;
  const user_id = str(form, "user_id");
  if (!user_id) return;
  const ctx = await getOrgContext();
  const supabase = await supabaseServer();
  await supabase.from("memberships").delete().eq("org_id", ctx.org.id).eq("user_id", user_id);
  revalidatePath("/app/settings");
}

export async function acceptInvitation(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const token = str(form, "token");
  if (!token) return { error: "This link is missing its invitation code." };
  const supabase = await supabaseServer();
  const { data, error } = await supabase.rpc("accept_invitation", { invite_token: token });
  if (error) return { error: explain(error.message) };
  await setActiveOrg(data);
  redirect("/app");
}
