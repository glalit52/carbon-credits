import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Every page is per user and per organisation, read through row-level
  // security, so there is nothing to prerender or share between requests.
  // Plain dynamic rendering is the honest default; cacheComponents is off.
  cacheComponents: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  serverExternalPackages: [],
  experimental: {
    serverActions: { bodySizeLimit: "25mb" }, // evidence photos and bulk imports
  },
  // One address for everything: requests to any host in LEGACY_HOSTS (a
  // comma-separated list) are sent permanently to the same path on
  // NEXT_PUBLIC_SITE_URL, so old links keep working and cookies, email links
  // and redirects only ever live on the canonical domain.
  async redirects() {
    const site = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "");
    const legacy = (process.env.LEGACY_HOSTS ?? "").split(",").map((h) => h.trim()).filter(Boolean);
    if (!site) return [];
    return legacy.map((host) => ({
      source: "/:path*",
      has: [{ type: "host" as const, value: host }],
      destination: `${site}/:path*`,
      permanent: true,
    }));
  },
  // Self-hosted Supabase (deploy/railway): the app is the gateway. Email links
  // and signed file URLs reach auth and storage through these, and the server
  // itself reaches all three through them on loopback. Unset on Supabase cloud.
  async rewrites() {
    const upstreams: [string, string | undefined][] = [
      ["/auth/v1", process.env.SUPABASE_AUTH_UPSTREAM],
      ["/rest/v1", process.env.SUPABASE_REST_UPSTREAM],
      ["/storage/v1", process.env.SUPABASE_STORAGE_UPSTREAM],
    ];
    return upstreams
      .filter((u): u is [string, string] => Boolean(u[1]))
      .map(([prefix, to]) => ({ source: `${prefix}/:path*`, destination: `${to.replace(/\/$/, "")}/:path*` }));
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Nothing here is meant to be framed; this stops a login page being overlaid for clickjacking.
          { key: "X-Frame-Options", value: "DENY" },
          // The field app walks boundaries with GPS and photographs forms; nothing needs the microphone.
          { key: "Permissions-Policy", value: "geolocation=(self), camera=(self), microphone=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
