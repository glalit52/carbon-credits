import { ArrowRight, BadgeCheck, FileSpreadsheet, Map, Satellite, ShieldCheck, Wallet } from "lucide-react";

import { Logo } from "@/components/logo";
import { ButtonLink, Card } from "@/components/ui";
import { DEMO } from "@/lib/env";

const FEATURES = [
  {
    icon: Map,
    title: "Enrol farms where they are",
    body: "Draw a boundary on satellite imagery, walk it with a phone's GPS, or upload KML, GeoJSON, WKT or a spreadsheet. Every boundary is checked before it is saved.",
  },
  {
    icon: FileSpreadsheet,
    title: "Bring your existing records",
    body: "Import thousands of farms, farmers, practice logs and soil lab results at once, with every row and every problem shown before anything is written.",
  },
  {
    icon: Satellite,
    title: "An estimate for every farm",
    body: "Each farm is quantified on its own climate and crop calendar under VM0051 (rice) or VM0047 (trees), with every generic assumption named.",
  },
  {
    icon: BadgeCheck,
    title: "Four-eyes review",
    body: "Vintages move draft → review → approved → issued. Nobody approves their own submission, and every step is in an append-only log.",
  },
  {
    icon: Wallet,
    title: "Farmers get paid",
    body: "Split issued credits by each farm's contribution, approve, and record each payout against the farmer who earned it.",
  },
  {
    icon: ShieldCheck,
    title: "Built for audit",
    body: "Per-organisation isolation enforced in the database, roles for field agents through reviewers, and a derivation behind every tonne.",
  },
];

export default function Home() {
  return (
    <div className="mx-auto flex min-h-dvh max-w-6xl flex-col px-5">
      <header className="flex items-center justify-between py-5">
        <Logo />
        <nav className="flex items-center gap-2">
          {!DEMO && (
            <ButtonLink href="/login" variant="ghost">
              Sign in
            </ButtonLink>
          )}
          <ButtonLink href={DEMO ? "/app" : "/signup"}>{DEMO ? "Open the demo" : "Get started"}</ButtonLink>
        </nav>
      </header>

      <main className="flex-1">
        <section className="py-16 sm:py-24">
          <p className="mb-3 text-sm font-medium text-brand">Digital MRV for smallholder carbon</p>
          <h1 className="max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
            From a farm boundary to a paid farmer, with every tonne explained.
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-muted">
            Enrol farms, bring in the data you already have, estimate credits on each farm&apos;s own climate,
            review vintages with a second pair of eyes, and pay the people who did the work.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href={DEMO ? "/app" : "/signup"} className="px-5 py-2.5">
              {DEMO ? "Explore the demo organisation" : "Create your organisation"} <ArrowRight className="h-4 w-4" />
            </ButtonLink>
            {!DEMO && (
              <ButtonLink href="/login" variant="secondary" className="px-5 py-2.5">
                I already have an account
              </ButtonLink>
            )}
          </div>
          {DEMO && (
            <p className="mt-4 text-sm text-muted">
              Running in demo mode: 18 farms around the Thanjavur and Nyeri pilots, estimated by the real engine.
              Read-only until Supabase is connected.
            </p>
          )}
        </section>

        <section className="grid gap-4 pb-20 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <Card key={title} className="p-5">
              <Icon className="h-5 w-5 text-brand" />
              <h2 className="mt-3 font-semibold">{title}</h2>
              <p className="mt-1.5 text-sm text-muted">{body}</p>
            </Card>
          ))}
        </section>
      </main>

      <footer className="border-t border-border py-6 text-xs text-muted">
        Monitoring is simulated from each farm&apos;s real climate until a satellite provider is connected; every
        estimate says so on its face.
      </footer>
    </div>
  );
}
