import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { SIGNED_IN_ONLY, SIGNED_OUT_ONLY, safeNext, under } from "@/lib/auth-shared";
import { DEMO, SUPABASE_ANON_KEY, SUPABASE_URL, siteUrl } from "@/lib/env";
import { MOCK_USER_COOKIE } from "@/lib/mock-creds";

/**
 * Keeps the Supabase session cookie fresh, sends signed-out visitors to the
 * login page and signed-in ones past it. This is the optimistic check only:
 * every page and action asks Supabase again (getOrgContext / requireUser),
 * and the database's own policies decide what is visible, so getting past
 * this file grants nothing.
 */
export async function proxy(request: NextRequest) {
  if (DEMO) return NextResponse.next();

  const mockCookie = request.cookies.get(MOCK_USER_COOKIE)?.value;

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
  const signedIn = Boolean(data?.claims?.sub) || Boolean(mockCookie);
  const path = request.nextUrl.pathname;

  // A redirect is a new response: carry over any refreshed session cookies.
  // Respect the current host so domains (e.g. web-production-c782e or custom domains) stay on themselves.
  const host = request.headers.get("x-forwarded-host") || request.nextUrl.host;
  const proto = request.headers.get("x-forwarded-proto") || request.nextUrl.protocol.replace(":", "") || "https";
  const origin = host ? `${proto}://${host}` : siteUrl();

  const go = (pathname: string, search = "") => {
    const redirect = NextResponse.redirect(new URL(pathname + search, origin));
    for (const c of response.cookies.getAll()) redirect.cookies.set(c);
    return redirect;
  };

  if (!signedIn && under(path, SIGNED_IN_ONLY)) {
    return go("/login", `?next=${encodeURIComponent(path + request.nextUrl.search)}`);
  }
  // Page loads only: a form posted from a tab opened before signing in should still get its answer.
  if (signedIn && request.method === "GET" && under(path, SIGNED_OUT_ONLY)) {
    const next = new URL(safeNext(request.nextUrl.searchParams.get("next")), origin);
    return go(next.pathname, next.search);
  }

  // Signed-in pages are per user: never let a shared cache keep one.
  if (signedIn && under(path, SIGNED_IN_ONLY)) response.headers.set("Cache-Control", "private, no-store");
  return response;
}

export const config = {
  // auth/v1, rest/v1 and storage/v1 are the self-hosted Supabase rewrites: they carry their own tokens.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|auth/v1|rest/v1|storage/v1|.*\\.(?:png|jpg|svg|webp|ico)$).*)"],
};
