# Web app

The front end for carbonstack: sign-up and organisations, farm enrolment on a
map, bulk import of existing records, per-farm credit estimates from the
engine, four-eyes vintage review, issuance and farmer payments.

Next.js 16 (App Router) + TypeScript + Tailwind, Supabase for auth, data and
files, MapLibre + terra-draw for maps, Recharts for charts.

## Run it

```bash
cd web
npm install
npm run dev          # http://localhost:3000
```

With no Supabase settings it runs in **demo mode**: a read-only organisation of
18 farms around the Thanjavur and Nyeri pilots, built by the real engine
(`python3 scripts/build_web_demo.py` regenerates it). Every page works; every
write says it is the demo.

## Connect Supabase

1. Create a project at supabase.com.
2. Run the migrations, in order, in the SQL editor (or `supabase db push`):
   `supabase/migrations/20261029000001_core.sql`, `…02_storage.sql`, `…03_claims.sql`, then
   `20261030000004_field.sql`.
3. Authentication → URL configuration: set the site URL and add
   `https://<your-domain>/auth/callback` to the redirect URLs.
4. Optional: Authentication → Providers → Google, for "Continue with Google".
5. Copy `.env.example` to `.env.local` and fill in the URL and anon key.

The first person to sign up creates an organisation and becomes its owner;
everyone else joins through an invitation link from Settings.

## Connect the engine

Estimates come from the Python engine's `POST /api/estimate` (see
`src/carbonstack/estimate.py`); forecasts, logger files, the scene catalogue
and registry reconciliation from `/api/forecast`, `/api/sensors`, `/api/scenes`
and `/api/reconcile`. All are stateless. Deploy the repository root to Vercel as it
already is, set `CARBONSTACK_ENGINE_TOKEN` there, and give the web app the same
token plus `CARBONSTACK_ENGINE_URL`. The engine fetches ten years of ERA5
weather from Open-Meteo for each farm (NASA POWER as fallback).

## Deploy

A second Vercel project with **Root Directory = `web`**, the env vars above,
and nothing else. The engine project at the repository root is unchanged.

## How access works

Every table is scoped to an organisation, and Postgres row-level security
enforces it. The browser and the server both talk to Supabase with the signed-in
user's own token, never a service key, so a bug in a page cannot leak another
organisation's farms. Roles:

| Role | Can |
|---|---|
| Owner | everything, including other owners |
| Admin | members, payments, issuance, all data |
| Reviewer | approve or hold vintages — never one they submitted |
| Analyst | projects, estimates, imports; submit vintages |
| Field agent | enrol farmers and farms, record practices and soil samples |
| Viewer | read only |

Vintage status changes go only through `transition_vintage()`, which enforces
the order (draft → submitted → approved → issued, with on-hold), the second
approver, and serial allocation. Every change to a commercial record is written
to `audit_events` by trigger; nobody, admins included, can edit or delete it.

## Selling forward, claims and verification

- **Forward sales** (project → Forward sales) runs the engine's delivery
  simulation (`POST /api/forecast`) on the project's estimates: farmer
  dropout, lapsed seasons, failed plantings and slipped verification, across
  4,000 seeded futures. It reports the volume that is safe to promise at the
  chosen confidence, which risk costs the most, how the safe share grows with
  more farmers, and whether a proposed sale is signable.
- **Claims & retirement** records Article 6 authorisations and the
  corresponding adjustments a host country actually reports, and retires
  credits in serial order. `retire_credits()` refuses to retire anything as an
  offset or for CORSIA unless an adjustment stands behind it; everything else
  can only be retired as a contribution. Each retirement keeps the exact
  claim wording it was issued with.
- **Public verification** at `/verify` and `/certificate/<id>` needs no
  account. Credit codes look like `7C3E9A51-2025-6`: the issuer's prefix, the
  vintage year and the serial. The lookups are two Postgres functions granted
  to `anon`, and they return registry facts only, never farmer or farm data.

## Monitoring, evidence and the registry

- **Monitoring** (farm → Monitoring) shows the series each estimate was built
  from. For rice it shows every Sentinel-1 pass, the detector's water call, the
  dry spells and how much each season's adoption confidence earned. For trees
  it shows canopy height and its error band. Rice farms take water-level
  logger exports, which the engine cleans for gaps, flatlines and spikes and
  then scores the radar against. The scene catalogue reports which Sentinel
  scenes actually exist over a farm and the longest blind gap between them.
- **Evidence pack** (vintage → Evidence pack) is a zip with:
  - a plot register, boundaries, and each farm's full engine record
  - radar passes, water regimes and logger summaries
  - practice records with their photos, and soil samples
  - the review trail, the audit log, payments, retirements and the claim basis
  - a SHA-256 manifest of every file

  The pack uses the estimate rows the vintage was built from, not whatever is
  latest.
- **Registry reconciliation** (Credits → Reconcile with registry) matches
  issued vintages against a Verra, Gold Standard, Puro or Isometric CSV export,
  by serial, then registry reference, then vintage and quantity. It lists every
  disagreement. Record the registry's reference on each issued vintage so
  matches don't rest on quantity alone.

## Field app and farmer statements

- **`/field`** is a phone-first enrolment flow for field agents:
  1. Pick or register the farmer, with consent and a photo of the form.
  2. Walk the boundary with GPS. A sketch is drawn from the corners, so no map
     tiles are needed.
  3. Record tenure, with a photo of the land record, and water control.

  The flow works offline. Enrolments wait in the phone's IndexedDB and send
  themselves when there is signal. Each carries an id from the phone, so a
  resend can never create the farm twice. In a production build, a service
  worker keeps the pages available offline. Rice farms take the crop calendar
  most of their project uses.
- **Statements** (farmer → Statement) show a farmer's fields, estimates,
  payments and missing paperwork, in English, Hindi, Tamil or Swahili.
  - A share link opens without an account. It expires (90 days by default, a
    year at most) and can be revoked.
  - It is served by one Postgres function that returns only that farmer's own
    summary: no boundaries, phone or account numbers.
  - "Send on WhatsApp" pre-fills a message in the farmer's language.
- **Translations** (`src/lib/i18n.ts`): the Hindi, Tamil and Swahili strings
  are a first draft. Have a native speaker on the team review them before
  farmers see them.

## Checks

```bash
npm run typecheck && npm run lint && npm test && npm run build
PGHOST=… PGUSER=postgres ../supabase/tests/run.sh   # RLS tests on a scratch DB
```

## What is not real yet

- **Monitoring is simulated**, from each farm's real climate and crop calendar.
  The engine can list Sentinel scenes for a farm but does not yet read pixel
  values from them. Every estimate says so on its face.
- **Generic inputs** (IPCC Tier 1 rice baseline, default tree growth) are used
  where a farm has no local figure, and each one is listed on the farm page.
- **No outgoing email or payouts**: invitation links are shown to the admin to
  share, and payments are marked paid by hand with the transaction reference.
