import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { DEMO, SUPABASE_ANON_KEY, SUPABASE_URL } from "@/lib/env";

/**
 * Keeps the Supabase session cookie fresh and sends signed-out visitors to
 * the login page. This is the optimistic check only: every page and action
 * asks Supabase again, and the database's own policies decide what is
 * visible, so getting past this file grants nothing.
 */
export async function proxy(request: NextRequest) {
  if (DEMO) return NextResponse.next();

  let response = NextResponse.next({ request });
  const supabase = createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (toSet) => {
        for (const { name, value } of toSet) request.cookies.set(name, value);
        response = NextResponse.next({ request });
        for (const { name, value, options } of toSet) response.cookies.set(name, value, options);
      },
    },
  });

  const { data } = await supabase.auth.getClaims();
  const signedIn = Boolean(data?.claims?.sub);
  const path = request.nextUrl.pathname;

  const guarded = ["/app", "/field", "/onboarding"].some((p) => path === p || path.startsWith(`${p}/`));
  if (!signedIn && guarded) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(path + request.nextUrl.search)}`;
    return NextResponse.redirect(url);
  }
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|svg|webp|ico)$).*)"],
};
