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
};

export default nextConfig;
