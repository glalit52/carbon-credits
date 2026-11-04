import { NextResponse, type NextRequest } from "next/server";

import { DEMO } from "@/lib/env";
import { supabaseServer } from "@/lib/supabase/server";

/** Where email links and Google sign-in land: trade the code for a session. */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const raw = searchParams.get("next") ?? "/app";
  const next = raw.startsWith("/") && !raw.startsWith("//") ? raw : "/app";
  const code = searchParams.get("code");
  if (DEMO || !code) return NextResponse.redirect(`${origin}/login`);

  const supabase = await supabaseServer();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent(error.message)}`);
  }
  return NextResponse.redirect(`${origin}${next}`);
}
