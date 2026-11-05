import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/env";

export default function robots(): MetadataRoute.Robots {
  const base = siteUrl().replace(/\/$/, "");
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/login", "/verify", "/verify/*", "/certificate/*"],
        disallow: ["/app/", "/app/*", "/auth/*", "/s/*", "/invite/*"],
      },
    ],
    sitemap: `${base}/sitemap.xml`,
  };
}

