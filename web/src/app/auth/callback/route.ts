import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";

import { safeNext } from "@/lib/auth-shared";
import { DEMO, siteUrl } from "@/lib/env";
import { supabaseServer } from "@/lib/supabase/server";

/**
 * Where email links and Google sign-in land. Two shapes arrive here:
 *  - `?code=` (PKCE): Google, and the default email templates. Works only in
 *    the browser that started the flow, since it holds the code verifier.
 *  - `?token_hash=&type=`: email templates that link here directly. Works in
 *    any browser, which matters when a farmer's phone opens the link.
 * A reset link always ends on /reset-password, whatever `next` says.
 */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  // Behind Railway's proxy the request's own origin is the container's
  // (https://localhost:8080), so every redirect goes to the configured site.
  const origin = siteUrl().replace(/\/$/, "");
  const failed = (message: string) =>
    NextResponse.redirect(`${origin}/login?error=${encodeURIComponent(message)}`);

  // Supabase redirects back with these when the link itself was bad or expired.
  const upstream = searchParams.get("error_description") ?? searchParams.get("error");
  if (upstream) return failed(upstream);

  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  if (DEMO || (!code && !(tokenHash && type))) return NextResponse.redirect(`${origin}/login`);

  const supabase = await supabaseServer();
  const { error } = code
    ? await supabase.auth.exchangeCodeForSession(code)
    : await supabase.auth.verifyOtp({ token_hash: tokenHash!, type: type! });
  if (error) return failed(error.message);

  const next = type === "recovery" ? "/reset-password" : safeNext(searchParams.get("next"));
  return NextResponse.redirect(`${origin}${next}`);
}
