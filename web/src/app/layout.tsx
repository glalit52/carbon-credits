import type { Metadata, Viewport } from "next";

import { APP_NAME, siteUrl } from "@/lib/env";

import "./globals.css";

const description =
  "Enrol farms, monitor practices with radar satellites, quantify verified carbon credits, and settle farmer payouts with every number traceable to source.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  title: {
    default: `${APP_NAME} · Digital MRV & Carbon Credit Operating System`,
    template: `%s · ${APP_NAME}`,
  },
  description,
  keywords: [
    "carbon credits",
    "dMRV",
    "digital MRV",
    "regenerative agriculture",
    "carbon accounting",
    "VM0051",
    "VM0047",
    "Verra",
    "Article 6",
    "rice methane",
    "agroforestry",
    "soil carbon",
  ],
  authors: [{ name: "Carbonstack Team" }],
  creator: APP_NAME,
  publisher: APP_NAME,
  openGraph: {
    type: "website",
    locale: "en_US",
    url: siteUrl(),
    siteName: APP_NAME,
    title: `${APP_NAME} · Digital MRV & Carbon Credit Operating System`,
    description,
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: `${APP_NAME} Digital MRV Platform`,
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: `${APP_NAME} · Digital MRV & Carbon Credit Operating System`,
    description,
    images: ["/og-image.png"],
    creator: "@carbonstack",
  },
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/icon.svg", type: "image/svg+xml" },
    ],
    apple: [{ url: "/apple-touch-icon.svg" }],
    shortcut: ["/favicon.ico"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f7f4" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1411" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}
