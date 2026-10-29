import type { Metadata } from "next";

import { Badge, Card, PageHeader } from "@/components/ui";
import { toggleIntegration } from "@/lib/actions/integrations";
import { getOrgContext, listIntegrations } from "@/lib/data";
import { DEMO, engineConfig } from "@/lib/env";
import { fmt } from "@/lib/format";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Integrations" };

type State = "connected" | "available" | "setup" | "planned";

const STATE: Record<State, { label: string; tone: "brand" | "info" | "accent" | "neutral" }> = {
  connected: { label: "Connected", tone: "brand" },
  available: { label: "In the engine", tone: "info" },
  setup: { label: "Needs setup", tone: "accent" },
  planned: { label: "Planned", tone: "neutral" },
};

export default async function IntegrationsPage() {
  const ctx = await getOrgContext();
  const rows = await listIntegrations(ctx.org.id);
  const stored = new Map(rows.map((r) => [r.provider, r]));
  const engine = engineConfig();

  // Status is decided by what the code and configuration can actually do,
  // not by a flag someone set: a connector says "connected" only if it runs.
  const groups: { title: string; items: { id: string; name: string; what: string; state: State; how: string; toggle?: boolean }[] }[] = [
    {
      title: "Platform",
      items: [
        {
          id: "supabase",
          name: "Supabase",
          what: "Database, sign-in and evidence file storage, with per-organisation access enforced in Postgres.",
          state: DEMO ? "setup" : "connected",
          how: DEMO ? "Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY, then run the migrations." : "Configured.",
        },
        {
          id: "engine",
          name: "Carbonstack estimate engine",
          what: "Quantifies each farm under VM0051 or VM0047 on its own climate and calendar (POST /api/estimate).",
          state: engine ? "connected" : "setup",
          how: engine ? `Calling ${engine.url}` : "Set CARBONSTACK_ENGINE_URL and CARBONSTACK_ENGINE_TOKEN.",
        },
        {
          id: "google-auth",
          name: "Google sign-in",
          what: "Lets people sign in with their Google account.",
          state: DEMO ? "setup" : "available",
          how: "Enable the Google provider in Supabase → Authentication → Providers.",
        },
      ],
    },
    {
      title: "Data sources",
      items: [
        {
          id: "open-meteo",
          name: "Open-Meteo (ERA5)",
          what: "Ten years of daily weather for each farm's centre, aggregated to monthly climate. Used by every estimate.",
          state: engine ? "connected" : "available",
          how: "No key needed. Every fetch is pinned with a hash in the estimate's record.",
          toggle: true,
        },
        {
          id: "nasa-power",
          name: "NASA POWER",
          what: "Monthly climate fallback when Open-Meteo cannot answer.",
          state: engine ? "connected" : "available",
          how: "No key needed. Used automatically.",
          toggle: true,
        },
        {
          id: "soilgrids",
          name: "ISRIC SoilGrids 2.0",
          what: "Soil organic carbon and texture prior for soil-carbon baselines.",
          state: "available",
          how: "In the engine (carbonstack data soil); not yet run from the app.",
        },
        {
          id: "sentinel-stac",
          name: "Sentinel-1 / Sentinel-2 catalogue",
          what: "Which radar and optical scenes cover a farm and when. Radar is what sees through monsoon cloud.",
          state: "available",
          how: "Scene search is in the engine (carbonstack data imagery). Retrieving pixel values is the next step; until then monitoring is simulated and every estimate says so.",
        },
        {
          id: "field-sensors",
          name: "Field water-level loggers",
          what: "Validates radar-detected dry-downs against tubes in the field.",
          state: "available",
          how: "CSV ingest and validation are in the engine (carbonstack sensors).",
        },
      ],
    },
    {
      title: "Registries and money",
      items: [
        {
          id: "verra-registry",
          name: "Verra / Gold Standard registry exports",
          what: "Reconciles registry issuance CSVs against this ledger, serial by serial.",
          state: "available",
          how: "In the engine (carbonstack registry reconcile).",
        },
        {
          id: "payouts",
          name: "Payout rails (UPI, M-Pesa, bank)",
          what: "Push approved farmer payments out and record the transaction id automatically.",
          state: "planned",
          how: "Today payments are marked paid by hand with the transaction reference.",
        },
        {
          id: "email",
          name: "Email delivery",
          what: "Sends invitations and review notifications.",
          state: "planned",
          how: "Invitation links are shown to the admin to share; set up SMTP in Supabase for auth emails.",
        },
        {
          id: "api",
          name: "Public API and webhooks",
          what: "Push farms in from your own field app; get notified when a vintage changes.",
          state: "planned",
          how: "Supabase's REST API already works with a member's token, under the same access rules.",
        },
      ],
    },
  ];

  return (
    <>
      <PageHeader
        title="Integrations"
        description="Where each number comes from. A source says “Connected” only if it is wired in and runs today."
      />
      <div className="flex flex-col gap-8">
        {groups.map((g) => (
          <section key={g.title}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">{g.title}</h2>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {g.items.map((it) => {
                const row = stored.get(it.id);
                const disabled = row && !row.enabled;
                return (
                  <Card key={it.id} className="flex flex-col p-5">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="font-semibold">{it.name}</h3>
                      <Badge tone={disabled ? "neutral" : STATE[it.state].tone}>{disabled ? "Off" : STATE[it.state].label}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-muted">{it.what}</p>
                    <p className="mt-3 text-xs">{it.how}</p>
                    {row?.last_status && (
                      <p className="mt-2 text-xs text-muted">
                        Last run {fmt.datetime(row.last_sync_at)}: {row.last_status}
                      </p>
                    )}
                    {it.toggle && can.administer(ctx.role) && (
                      <form action={toggleIntegration} className="mt-auto pt-4">
                        <input type="hidden" name="provider" value={it.id} />
                        <input type="hidden" name="enabled" value={disabled ? "true" : "false"} />
                        <button className="text-xs font-medium text-brand hover:underline" disabled={ctx.demo}>
                          {disabled ? "Turn on" : "Turn off"}
                        </button>
                      </form>
                    )}
                  </Card>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
