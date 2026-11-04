import type { PaymentStatus, VintageStatus } from "@/lib/database.types";

const nf = (digits: number) =>
  new Intl.NumberFormat("en", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const fmt = {
  t: (n: number | null | undefined, digits = 1) => (n == null ? "—" : `${nf(digits).format(Number(n))} t`),
  ha: (n: number | null | undefined) => (n == null ? "—" : `${nf(2).format(Number(n))} ha`),
  int: (n: number | null | undefined) => (n == null ? "—" : nf(0).format(Number(n))),
  num: (n: number | null | undefined, digits = 2) => (n == null ? "—" : nf(digits).format(Number(n))),
  pct: (n: number | null | undefined, digits = 0) => (n == null ? "—" : `${nf(digits).format(Number(n) * 100)}%`),
  money: (n: number | null | undefined, currency = "USD") =>
    n == null
      ? "—"
      : new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(n)),
  date: (s: string | null | undefined) =>
    s ? new Date(s.length === 10 ? `${s}T00:00:00Z` : s).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "—",
  datetime: (s: string | null | undefined) =>
    s
      ? new Date(s).toLocaleString("en-GB", {
          day: "numeric",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "UTC",
        }) + " UTC"
      : "—",
};

export const VINTAGE_LABEL: Record<VintageStatus, string> = {
  draft: "Draft",
  submitted: "In review",
  approved: "Approved",
  on_hold: "On hold",
  issued: "Issued",
};

export const VINTAGE_TONE = {
  draft: "neutral",
  submitted: "info",
  approved: "brand",
  on_hold: "accent",
  issued: "brand",
} as const satisfies Record<VintageStatus, string>;

export const PAYMENT_TONE = {
  pending: "neutral",
  approved: "info",
  paid: "brand",
  failed: "danger",
} as const satisfies Record<PaymentStatus, string>;

export const PATHWAY_LABEL: Record<string, string> = {
  rice: "Rice methane (AWD)",
  agroforestry: "Agroforestry",
  soil: "Soil carbon",
  other: "Other",
};

export const TENURE_LABEL: Record<string, string> = {
  owned_title: "Owned (title)",
  registered_lease: "Registered lease",
  community_right: "Community right",
  grama_sabha_consent: "Grama sabha consent",
  undocumented: "Undocumented",
};

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
