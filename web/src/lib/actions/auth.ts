"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ACTIVE_ORG_COOKIE } from "@/lib/data";
import { siteUrl } from "@/lib/env";
import { supabaseServer } from "@/lib/supabase/server";

import { type ActionResult, refuseInDemo, str } from "./result";

/** Only same-site paths, so a crafted ?next= cannot bounce a login elsewhere. */
function safeNext(next: string | null, fallback = "/app"): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : fallback;
}

export async function signIn(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const email = str(form, "email");
  const password = str(form, "password");
  if (!email || !password) return { error: "Enter your email and password." };
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) return { error: error.message };
  redirect(safeNext(str(form, "next")));
}

export async function signUp(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const email = str(form, "email");
  const password = str(form, "password");
  const full_name = str(form, "full_name");
  if (!email || !password || !full_name) return { error: "Name, email and password are all required." };
  if (password.length < 10) return { error: "Use a password of at least 10 characters." };
  const next = safeNext(str(form, "next"), "/onboarding");
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: { full_name },
      emailRedirectTo: `${siteUrl()}/auth/callback?next=${encodeURIComponent(next)}`,
    },
  });
  if (error) return { error: error.message };
  if (data.session) redirect(next);
  return { message: `We sent a confirmation link to ${email}. Open it to finish signing up.` };
}

export async function sendMagicLink(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const email = str(form, "email");
  if (!email) return { error: "Enter your email." };
  const next = safeNext(str(form, "next"));
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: {
      shouldCreateUser: false,
      emailRedirectTo: `${siteUrl()}/auth/callback?next=${encodeURIComponent(next)}`,
    },
  });
  if (error) return { error: error.message };
  return { message: `If ${email} has an account, a sign-in link is on its way.` };
}

export async function signInWithGoogle(form: FormData): Promise<void> {
  if (refuseInDemo()) redirect("/login?demo=1");
  const next = safeNext(str(form, "next"));
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: `${siteUrl()}/auth/callback?next=${encodeURIComponent(next)}` },
  });
  if (error || !data.url) redirect(`/login?error=${encodeURIComponent(error?.message ?? "Google sign-in failed")}`);
  redirect(data.url);
}

export async function signOut(): Promise<void> {
  if (!refuseInDemo()) {
    const supabase = await supabaseServer();
    await supabase.auth.signOut();
    (await cookies()).delete(ACTIVE_ORG_COOKIE);
  }
  redirect("/login");
}

export async function requestPasswordReset(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const email = str(form, "email");
  if (!email) return { error: "Enter your email." };
  const supabase = await supabaseServer();
  await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${siteUrl()}/auth/callback?next=/app/account`,
  });
  return { message: `If ${email} has an account, a reset link is on its way.` };
}

export async function updatePassword(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const password = str(form, "password");
  if (!password || password.length < 10) return { error: "Use a password of at least 10 characters." };
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.updateUser({ password });
  return error ? { error: error.message } : { message: "Password updated." };
}
