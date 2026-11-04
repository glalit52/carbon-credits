// Configuration, read once. Without Supabase settings the app runs in demo
// mode: a read-only organisation built from sample data, so a fresh deploy
// shows something real before anyone has set up a database.

// Self-hosted (deploy/railway): the server reaches auth, rest and storage
// through its own rewrites on loopback, so SUPABASE_INTERNAL_URL is
// http://127.0.0.1:<port>. Only the server talks to Supabase -- the browser
// never does -- so the session cookie is named after this one URL throughout.
export const SUPABASE_URL = process.env.SUPABASE_INTERNAL_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || "";
export const SUPABASE_ANON_KEY =
  process.env.SUPABASE_ANON_KEY ||
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
  "";

export const DEMO = !SUPABASE_URL || !SUPABASE_ANON_KEY;

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Carbonstack";

/** The Python engine (api/index.py) and the token it expects. Server only. */
export function engineConfig(): { url: string; token: string } | null {
  const url = process.env.CARBONSTACK_ENGINE_URL;
  const token = process.env.CARBONSTACK_ENGINE_TOKEN;
  return url && token ? { url: url.replace(/\/$/, ""), token } : null;
}

export function siteUrl(): string {
  return (
    process.env.NEXT_PUBLIC_SITE_URL ??
    (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3000")
  );
}

/** Hide "Continue with Google" where the provider is not configured (AUTH_GOOGLE_ENABLED=false). */
export const GOOGLE_SIGN_IN = process.env.AUTH_GOOGLE_ENABLED !== "false";
