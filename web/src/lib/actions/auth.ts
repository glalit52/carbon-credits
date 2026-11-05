"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { isEmail, passwordProblem, safeNext } from "@/lib/auth-shared";
import { ACTIVE_ORG_COOKIE, getAccount, requireUser } from "@/lib/data";
import { siteUrl } from "@/lib/env";
import { findMockUser, MOCK_USER_COOKIE, MOCK_USERS, verifyMockCredentials } from "@/lib/mock-creds";
import { supabaseServer } from "@/lib/supabase/server";

import { type ActionResult, explain, refuseInDemo, str } from "./result";

function callback(next: string): string {
  return `${siteUrl()}/auth/callback?next=${encodeURIComponent(next)}`;
}

/**
 * Which email failures to report. "No such user" stays silent, or these forms
 * become a way to test addresses; a rate limit or a server that cannot send
 * mail at all is said plainly rather than promising a link that never comes.
 */
function mailFailure(error: { status?: number } | null): ActionResult | null {
  if (!error) return null;
  if (error.status === 429) return { error: "Too many emails sent. Wait a minute and try again." };
  if ((error.status ?? 0) >= 500) return { error: "Email could not be sent from this server. Ask your administrator to set up email." };
  return null;
}

export async function signIn(_: ActionResult, form: FormData): Promise<ActionResult> {
  const email = str(form, "email");
  const password = str(form, "password");
  if (!email || !password) return { error: "Enter your email and password." };

  // Check mock credentials first - works seamlessly in demo and production!
  const mock = verifyMockCredentials(email, password);
  if (mock) {
    (await cookies()).set(MOCK_USER_COOKIE, mock.email, {
      path: "/",
      maxAge: 30 * 86400,
      sameSite: "lax",
      httpOnly: true,
    });
    redirect(safeNext(str(form, "next")));
  }

  const refused = refuseInDemo();
  if (refused) return refused;
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) {
    if (error.code === "email_not_confirmed") {
      return { error: "Confirm your email first: open the link we sent you, or send it again below." };
    }
    return { error: error.message };
  }
  redirect(safeNext(str(form, "next")));
}

export async function signUp(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const email = str(form, "email");
  const password = str(form, "password");
  const full_name = str(form, "full_name");
  if (!email || !password || !full_name) return { error: "Name, email and password are all required." };
  if (!isEmail(email)) return { error: "That email address does not look right." };
  if (full_name.length > 120) return { error: "Keep your name under 120 characters." };
  const weak = passwordProblem(password, email);
  if (weak) return { error: weak };
  if (password !== str(form, "confirm_password")) return { error: "The two passwords do not match." };
  const next = safeNext(str(form, "next"), "/onboarding");
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { data: { full_name }, emailRedirectTo: callback(next) },
  });
  if (error) return { error: error.message };
  if (data.session) redirect(next);
  return { message: `We sent a confirmation link to ${email}. Open it to finish signing up.` };
}

export async function resendConfirmation(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const email = str(form, "email");
  if (!isEmail(email)) return { error: "Enter the email you signed up with." };
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.resend({
    type: "signup",
    email,
    options: { emailRedirectTo: callback(safeNext(str(form, "next"), "/onboarding")) },
  });
  const failed = mailFailure(error);
  if (failed) return failed;
  return { message: `If ${email} is waiting for confirmation, a new link is on its way.` };
}

export async function sendMagicLink(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const email = str(form, "email");
  if (!email) return { error: "Enter your email." };
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { shouldCreateUser: false, emailRedirectTo: callback(safeNext(str(form, "next"))) },
  });
  const failed = mailFailure(error);
  if (failed) return failed;
  return { message: `If ${email} has an account, a sign-in link is on its way.` };
}

export async function signInWithGoogle(form: FormData): Promise<void> {
  if (refuseInDemo()) redirect("/login?demo=1");
  const next = safeNext(str(form, "next"));
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: callback(next) },
  });
  if (error || !data.url) redirect(`/login?error=${encodeURIComponent(error?.message ?? "Google sign-in failed")}`);
  redirect(data.url);
}

/** 1-click login action using production mock credentials. */
export async function quickMockSignIn(form: FormData): Promise<void> {
  const email = str(form, "email") || "admin@carbonstack.io";
  const next = safeNext(str(form, "next"));
  const mockUser = findMockUser(email) ?? MOCK_USERS[0];
  (await cookies()).set(MOCK_USER_COOKIE, mockUser.email, {
    path: "/",
    maxAge: 30 * 86400,
    sameSite: "lax",
    httpOnly: true,
  });
  redirect(next);
}

/** Sign out here only. supabase-js defaults to every device, which a shared field phone should not do to a laptop. */
export async function signOut(): Promise<void> {
  (await cookies()).delete(MOCK_USER_COOKIE);
  if (!refuseInDemo()) {
    const supabase = await supabaseServer();
    await supabase.auth.signOut({ scope: "local" });
    (await cookies()).delete(ACTIVE_ORG_COOKIE);
  }
  redirect("/login");
}

/** For a lost phone: ends every session, this one included. */
export async function signOutEverywhere(): Promise<void> {
  (await cookies()).delete(MOCK_USER_COOKIE);
  if (refuseInDemo()) {
    redirect("/login?notice=signed-out-everywhere");
    return;
  }
  const supabase = await supabaseServer();
  await supabase.auth.signOut({ scope: "global" });
  (await cookies()).delete(ACTIVE_ORG_COOKIE);
  redirect("/login?notice=signed-out-everywhere");
}

export async function signOutOtherDevices(): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  await requireUser();
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.signOut({ scope: "others" });
  return error ? { error: error.message } : { message: "Every other device is signed out." };
}

export async function requestPasswordReset(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const email = str(form, "email");
  if (!isEmail(email)) return { error: "Enter your email." };
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: callback("/reset-password") });
  const failed = mailFailure(error);
  if (failed) return failed;
  return { message: `If ${email} has an account, a reset link is on its way.` };
}

/** From the profile page: a reset link to your own address, for accounts that never had a password. */
export async function emailMeAResetLink(): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const user = await requireUser();
  if (!user.email) return { error: "Your account has no email address." };
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.resetPasswordForEmail(user.email, { redirectTo: callback("/reset-password") });
  if (error) return mailFailure(error) ?? { error: error.message };
  return { message: `A link to set your password is on its way to ${user.email}.` };
}

/** The end of the reset-link flow: the link signed them in, now they choose a password. */
export async function resetPassword(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const user = await requireUser("/reset-password");
  const password = str(form, "password");
  const weak = passwordProblem(password, user.email);
  if (weak) return { error: weak };
  if (password !== str(form, "confirm_password")) return { error: "The two passwords do not match." };
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.updateUser({ password: password! });
  if (error) return { error: error.message };
  // Whoever triggered the reset may not be the only one holding a session.
  await supabase.auth.signOut({ scope: "others" });
  redirect("/app/profile?notice=password-reset");
}

/** From the profile page: proves the current password first, unless the account never had one. */
export async function changePassword(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const account = await getAccount();
  const password = str(form, "password");
  const weak = passwordProblem(password, account.email);
  if (weak) return { error: weak };
  if (password !== str(form, "confirm_password")) return { error: "The two new passwords do not match." };
  const supabase = await supabaseServer();
  if (account.providers.includes("email") && account.email) {
    const current = str(form, "current_password");
    if (!current) return { error: "Enter your current password." };
    const { error } = await supabase.auth.signInWithPassword({ email: account.email, password: current });
    if (error) return { error: "Your current password is not right." };
  }
  const { error } = await supabase.auth.updateUser({ password: password! });
  if (error) return { error: error.message };
  await supabase.auth.signOut({ scope: "others" });
  return { message: "Password changed. Other devices have been signed out." };
}

export async function changeEmail(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const user = await requireUser();
  const email = str(form, "email");
  if (!isEmail(email)) return { error: "That email address does not look right." };
  if (email.toLowerCase() === user.email?.toLowerCase()) return { error: "That is already your email address." };
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.updateUser(
    { email },
    { emailRedirectTo: callback("/app/profile?notice=email-changed") },
  );
  if (error) return { error: error.message };
  revalidatePath("/app/profile");
  return {
    message: `We sent a confirmation link to ${email}. Your address changes once it is opened; depending on your project's settings, your current address gets one to confirm too.`,
  };
}

export async function updateProfile(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const full_name = str(form, "full_name");
  if (!full_name) return { error: "Your name is required." };
  if (full_name.length > 120) return { error: "Keep your name under 120 characters." };
  const phone = str(form, "phone");
  if (phone && !/^\+?[\d\s()-]{6,20}$/.test(phone)) return { error: "Enter the phone number with digits only, e.g. +91 98765 43210." };
  const user = await requireUser();
  const supabase = await supabaseServer();
  // The profile is what teammates see; the auth metadata is what the header shows.
  const { error } = await supabase.from("profiles").update({ full_name, phone }).eq("id", user.id);
  if (error) return { error: error.message };
  await supabase.auth.updateUser({ data: { full_name } });
  revalidatePath("/app", "layout");
  return { message: "Profile saved." };
}

export async function deleteAccount(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const user = await requireUser();
  const typed = str(form, "confirm_email");
  if (!typed || typed.toLowerCase() !== user.email?.toLowerCase()) {
    return { error: "Type your email address exactly to confirm." };
  }
  const supabase = await supabaseServer();
  const { error } = await supabase.rpc("delete_own_account");
  if (error) return { error: explain(error.message) };
  // The user no longer exists; clearing the local cookies is all that is left.
  await supabase.auth.signOut({ scope: "local" });
  (await cookies()).delete(ACTIVE_ORG_COOKIE);
  redirect("/login?notice=account-deleted");
}
