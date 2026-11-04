import { NextResponse, type NextRequest } from "next/server";

import { getOrgContext } from "@/lib/data";
import { DEMO } from "@/lib/env";
import { supabaseServer } from "@/lib/supabase/server";

/**
 * Open an evidence file. Files are private; this hands out a five-minute
 * signed link, and only for a path inside the caller's own organisation's
 * folder, which the storage policy enforces again on its side.
 */
export async function GET(request: NextRequest) {
  const path = request.nextUrl.searchParams.get("path") ?? "";
  if (DEMO) return NextResponse.json({ error: "The demo holds no evidence files." }, { status: 404 });
  const ctx = await getOrgContext();
  if (!path.startsWith(`${ctx.org.id}/`) || path.includes("..")) {
    return NextResponse.json({ error: "Not found." }, { status: 404 });
  }
  const supabase = await supabaseServer();
  const { data, error } = await supabase.storage.from("evidence").createSignedUrl(path, 300);
  if (error || !data) return NextResponse.json({ error: "Not found." }, { status: 404 });
  return NextResponse.redirect(data.signedUrl);
}
