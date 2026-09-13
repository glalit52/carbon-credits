# carbon-credits

Two products share this repository.

**`carbonstack`** — a carbon credit and reforestation project: the research
behind it, the financial model that gates it, and the dMRV core it runs on.
Everything below the first divider.

**`aicio`** — Personal AI CIO, an AI-native private investment banker built to
the PRD in `docs/aicio/`. It shares this repository's conventions (standard
library only, audited calculations, a generated static dashboard) and shares
nothing else with `carbonstack`: separate package, separate database, separate
deployment path under `/cio`. See [Personal AI CIO](#personal-ai-cio) and
[docs/aicio/architecture.md](docs/aicio/architecture.md).

## Where things are

| Path | What it is |
|---|---|
| `docs/research/` | Teardown of Mitti Labs and Varaha, and what it implies for us |
| `model/carbon_model.py` | Portfolio cashflow model — the go/no-go gate |
| `src/carbonstack/` | The product — see the map below |
| `src/carbonstack/sites.py` | The two pilot sites — real places, real climatology |
| `src/carbonstack/feed.py` | Simulated monitoring on the real 5-day revisit cadence |
| `dashboard/` | The live MRV dashboard, its dataset and example evidence packs |
| `scripts/` | Build the dashboard dataset and page |
| `src/aicio/` | Personal AI CIO — the second product, mapped below |
| `aicio_dashboard/` | Its generated dashboard, published under `/cio` |
| `docs/aicio/architecture.md` | Why the AI CIO is built the way it is |
| `tests/` | 481 tests, stdlib only |

## The two numbers that shape everything

The model says a cropland hectare grosses about **$13.77 a year** at 1.5
tCO2e/ha and $12/credit. After the farmer's share we keep **$6.20** — and
that is the entire budget for monitoring that hectare, forever. Scale does
not rescue it; at 10x the hectares the peak funding need grows to $89.8M,
because the per-hectare margin is negative to begin with.

A mature agroforestry hectare is the opposite: **+$33.90 a year** after
monitoring, but not until roughly year eight.

So the portfolio is one business with two clocks, and the product has a hard
design target rather than a vague one: **marginal monitoring cost under ~$6
per hectare per year.** That is why routine monitoring here is satellite-first
and batch-processed, with no per-plot human step. Field measurement exists to
calibrate the model, not to produce the numbers.

```bash
python3 model/carbon_model.py            # cashflow, peak funding need, sensitivity
```

## carbonstack

```bash
pip install -e ".[dev]"
python -m pytest                         # 140 tests

python -m carbonstack demo               # both tracks against synthetic monitoring
python -m carbonstack export estate --out project.json
python -m carbonstack eligibility project.json
python -m carbonstack quantify project.json --year 2031 --methodology VM0047
python -m carbonstack explain  project.json --year 2031
```

### What it does

**Quantifies credits under two methodologies.** `VM0047` (afforestation,
reforestation, revegetation — area-based) credits growth net of a dynamic
performance benchmark, exactly as the methodology requires: the baseline is
re-derived at each verification from what comparable land actually did, not
argued once in a project document. `VM0042` (improved agricultural land
management, including rice water management) credits practice adoption times
an emission factor.

**Refuses to credit what it cannot evidence.** A plot with undocumented
tenure, a tenure claim with no reference document, or a farmer with no
recorded consent is excluded from the creditable area and reported, not
quietly counted. On the demo portfolio that is 16.7% of enrolled hectares —
which is the point. Paperwork, not biology, is what usually delays issuance.

**Carries the derivation with the number.** Every quantity is returned as a
`Calculation`: inputs, equation, intermediate terms, deductions, sources, in
order. `explain` prints it. This is the whole commercial thesis in one
command — buyers are not paying for tonnes, they are paying for tonnes that
will survive scrutiny.

```
above-ground biomass                    101.3812 t DM/ha
                                        AGB = 1.0 * H^1.85
below-ground biomass                     27.3729 t DM/ha
carbon                                   60.5115 t C/ha
carbon dioxide equivalent               221.8755 tCO2e/ha
uncertainty (1 sigma)                    92.3123 tCO2e/ha
                                        height term 33.3%, allometry 25.0%, combined 41.6%
```

**Prices imprecision honestly.** Uncertainty propagates through the power-law
allometry (a 10% height error becomes an 18.5% biomass error), and anything
above the 15% allowance is deducted from issuable credits. Two consequences
fall straight out, and both are tested: a generic allometry costs real money
against a locally calibrated one, and a Tier 3 emission factor issues over
1.5x the credits of a Tier 1 factor **for identical physical abatement**.
That is the financial case for owning a measurement asset, which is what
Mitti Labs actually built.

**Treats adoption as a probability.** A satellite sees a dry-down with some
confidence, not a farmer's intention. Crediting a full hectare whenever
confidence clears a line is how cropland projects over-credit without anyone
lying; multiplying by confidence is the honest version, and it makes better
detection worth money.

### Structure

```
carbonstack/
  audit.py          Calculation and Term — the derivation, as a return value
  geo.py            geodesic area, centroid, boundary validation (no GIS deps)
  domain.py         Project, Farmer, Plot, Enrollment, Cohort, Observation
  biomass.py        canopy height -> AGB -> carbon -> CO2e, with error propagation
  remote_sensing.py Provider protocol, synthetic provider, field/satellite reconciliation
  sites.py          the two pilot sites — real places, real climatology
  feed.py           simulated monitoring on the real 5-day revisit cadence
  methodology/      VM0047 (ARR, dynamic benchmark) and VM0042 (practice-based)
  store/            SQLite schema, migrations, repositories, hash-chained events
  pipeline.py       batch monitoring, quantification, project health
  ledger.py         vintage lifecycle, issuance, serials, buffer pool
  payments.py       farmer revenue share, register, reconciliation
  evidence.py       the verification pack a VVB actually receives
  api.py            HTTP API, stdlib only
  cli.py            the whole lifecycle
```

The core is stdlib-only and installs anywhere — the same code has to run in a
notebook, a batch job and a field laptop.

## The two pilot sites

| | **Vallam, Thanjavur** | **Gatugi, Nyeri** |
|---|---|---|
| Where | Cauvery delta, Tamil Nadu | Central Highlands, Kenya |
| Size | 2.49 ha | 2.87 ha |
| Crop | Paddy rice, two seasons | Arabica under Grevillea shade |
| Pathway | Methane avoidance via AWD | Removal via shade agroforestry |
| Methodology | VM0042 | VM0047 |
| Credits at maturity | 1.17 tCO2e/yr | 57.2 tCO2e/yr |
| Gross revenue | **$14/yr** | **$1,487/yr** |
| MRV budget | **$2.53/ha/yr** | **$207/ha/yr** |
| Verdict | **−$39/yr** — never viable at any scale | **+$520/yr** — viable, needs ~1,050 ha |

Rice was chosen because it is India's single largest agricultural methane
source, so it is the highest-value place to prove an avoidance pathway. The
result is that at plot scale it does not pay for its own supervision: the
whole developer margin on that hectare is **$2.53 a year** against an assumed
$18 monitoring cost. Coffee agroforestry is the opposite — 20 tCO2e/ha at
maturity against a $207/ha monitoring budget.

Locations, climatology, crop calendars and methodology mechanics are real.
**Boundaries are drawn rather than surveyed and every monitored value is
simulated** on the real 5-day Sentinel-2 revisit cadence. No imagery was
retrieved. The feed is deterministic and runs past today, so each revisit date
that passes reveals a reading that was not previously visible.

```bash
python3 scripts/build_dashboard_data.py   # run the feed + engine, write data.json
python3 scripts/build_dashboard.py        # inline it into dashboard/index.html
```

## Running the lifecycle

```bash
carbonstack init
carbonstack enroll vallam
carbonstack monitor IN-TNJ-01 --to 2026-09-11
carbonstack quantify IN-TNJ-01 --year 2025 --tier 3 --actor lalit
carbonstack queue                                  # what is waiting on a human
carbonstack explain IN-TNJ-01:2025                 # where the number came from
carbonstack review IN-TNJ-01:2025 --submit  --actor lalit
carbonstack review IN-TNJ-01:2025 --approve --actor priya --note "3 dry-downs confirmed"
carbonstack issue  IN-TNJ-01:2025 --registry "Gold Standard" --actor priya
carbonstack pay raise IN-TNJ-01:2025 --price 12 --share 0.55 --actor lalit
carbonstack evidence IN-TNJ-01 --out packs/tnj
carbonstack verify
carbonstack serve                                  # HTTP API on :8000
```

### What the rules refuse, and why

The interesting part of a carbon platform is what it will not let you do.

- **Issuing a draft** — quantify-and-issue in one step is no control at all, so
  review is a separate act by a separate person.
- **Approving a warned vintage without a written reason** — a warning that
  blocks nothing is decoration. This is the only thing that makes them matter.
- **Re-quantifying an issued vintage** — the issued number is a commercial fact
  somebody has bought against. A recomputation that disagrees is an incident to
  investigate, not an update to apply.
- **Raising payments against credits that do not exist yet** — that is how a
  project ends up owing money it has not been paid.
- **Marking a payment paid with no reference** — a payment that cannot be
  reconciled against a bank statement is, for audit, a payment that did not
  happen.
- **Issuing fractional credits** — registries issue whole tonnes. The remainder
  is recorded as a carry, not dropped.

Each refusal exits non-zero and says which rule was broken.

### The event chain

Every state change writes an event, and each event's hash covers its own
content **and its predecessor's hash**. A row edited behind the application
breaks the chain, and `carbonstack verify` says where:

```
$ sqlite3 carbonstack.db "UPDATE vintages SET net_t = 99 WHERE id='IN-TNJ-01:2025'"
$ carbonstack verify
EVENT CHAIN BROKEN at event 3
  a row was changed outside the application
```

That is the difference between "our database says so" and something a verifier
can test for themselves. The evidence pack ships the log and its integrity
result — including when the result is *failed*, because a pack that hides a
broken chain is worse than no pack.

### The evidence pack

`carbonstack evidence` writes plain files a verification body can read without
installing anything: `plot_register.csv` (with the exclusion reason for every
blocked plot), `observations.csv`, `vintages.csv`, `issuances.csv`,
`payments.csv`, `derivations.json`, `event_log.csv`, a `manifest.json`, and a
readable `SUMMARY.md`. The faster a VVB can satisfy itself, the cheaper and
sooner the verification — which is the whole commercial argument.

## One record, two surfaces

The dashboard is not a second calculation of the same numbers — that is how two
screens end up disagreeing and nobody knows which is right. `scripts/build_dashboard_data.py`
runs the **actual** lifecycle into a real database (enrol, monitor, quantify,
review, approve, issue, raise payments, export evidence) and then reads the
result back out. Its *Chain of custody* section is the event log from that run,
and `dashboard/packs/` holds the evidence packs it produced on the way.

That run also demonstrates the governance working rather than being bypassed:
the paddy's 2025 vintage clears review and issues 1 credit with a $6.60 farmer
payment raised against it; the 2026 vintage carries the no-dry-down warning and
is **held**, not waved through. The coffee block has no settled vintage at all
yet — on a removal pathway that wait is the pathway, not a delay.

## Deploying

The repo is configured for Vercel. From a clone with the Vercel CLI installed
and logged in:

```bash
npx vercel link      # once, to attach the repo to a project
npx vercel --prod
```

Or import `glalit52/carbon-credits` at vercel.com/new — `vercel.json` supplies
the build command, output directory and routing, so there is nothing to
configure in the UI.

What gets published:

| Path | What |
|---|---|
| `/` | the dashboard, data embedded, no network needed |
| `/packs/<site>/` | the evidence packs, so a VVB can be sent a URL |
| `/api/...` | the read API over a committed demo database |

### The deployment is read-only, and says so

Vercel's filesystem is ephemeral and per-invocation. A write to SQLite there
would return 200 and then vanish when the container recycled — a vintage that
approves itself and later un-approves itself is far worse than one that
refuses. So **every POST returns 503** naming the reason and the fix:

```json
{
  "error": "this deployment is read-only",
  "reason": "Serverless storage here is ephemeral, so a write would look like
             it succeeded and then disappear. Refusing is the honest answer.",
  "fix": "Point the store at durable storage (Postgres, Turso, or managed
          SQLite), or run `carbonstack serve` on a host with a real disk."
}
```

Two ways to make writes real, when you want them:

1. **Keep serverless, move the storage.** `store/repo.py` is the only module
   that touches SQL. Swapping its connection for Postgres or Turso is a
   contained change, and the schema in `store/schema.py` is ordinary SQL.
2. **Run it on a real disk.** `carbonstack serve` on any small VM or container
   host works today with no changes — the API is the same code either way.

The static dashboard is unaffected by this: it embeds its data and needs no
backend at all.

## What is deliberately not real yet

Three placeholders are marked in the source and must be replaced before any
issuance. They are project milestones, not refinements:

1. **The allometric equation.** A generic stand fit at 25% error. Replace with
   a locally calibrated equation — this is the tree-project equivalent of a
   Tier 3 emission factor, and the tests show what it is worth.
2. **The performance benchmark.** Currently a constant. Replace with a
   Verra-vetted data service provider over a matched control population. A
   benchmark set near zero turns every project into a high performer, which is
   the failure mode VM0047 exists to close.
3. **The monitoring provider.** `SyntheticProvider` is deterministic fiction
   that proves the pipeline. The real one is Sentinel-2 optical plus
   Sentinel-1 SAR fused with GEDI spaceborne LiDAR, which drops into the same
   `Provider` interface without touching quantification.

Emission factors for cropland practices are likewise conservative placeholders
carrying Tier 1 uncertainty, which the engine already charges for.

## Open question

Reforestation is unfinanceable without provable long-horizon land rights, and
`eligibility` is built to enforce that. Which landscape, how many hectares,
and what tenure evidence exists is the input nothing else can substitute for.


---

# Personal AI CIO

An AI-native private investment banker. Not an investment-discovery app with a
chatbot attached: a system that continuously turns one person's whole financial
picture into a small number of explainable decisions, and that is willing to
conclude that no decision is needed.

```
python3 -m aicio demo            # seed a portfolio and run the whole product
python3 -m aicio evals           # the financial AI evaluation suite
python3 -m aicio serve           # the HTTP API on :8787
```

`demo` needs no configuration, no API key and no network.

## What it actually does

Run against the demo portfolio — ₹1.19 crore across six funds, three direct
stocks, EPF, gold and idle cash — it finds things a holdings screen cannot:

```
[high  ] REVIEW  Mirae Asset ELSS Tax Saver and UTI Nifty 50 Index Fund
                 overlap 100% -- you are paying twice for one exposure
[high  ] REVIEW  'Second home' has a 7% chance of being met on the current plan
[medium] REVIEW  Debt is -5.6% outside its band -- point contributions here
                 rather than selling elsewhere
[medium] REDUCE  Parag Parikh Flexi Cap is 16.5% of the portfolio
[low   ] REVIEW  Axis Bluechip no longer earns its place on the evidence
```

Ask it anything and the answer comes from the same engine output:

```
$ python3 -m aicio ask "what do I actually own?"
Your largest single-company exposure is HDFCBANK at 8.6% of the portfolio,
reaching you through 5 separate holdings. By sector: Fixed Income 17%,
Financials 9%, Energy 7%. Mirae Asset ELSS Tax Saver and UTI Nifty 50 Index
Fund overlap 100% of their disclosed holdings, so you are paying two expense
ratios for close to one exposure. Look-through covers 58% of your portfolio;
the remainder sits in funds that publish only their largest positions.
```

That 8.6% in one bank across five holdings is invisible on every holdings
screen the user owns. Finding it is the product.

## Structure

| Module | What it is |
|---|---|
| `domain.py` | The entities a personal balance sheet is made of |
| `provenance.py` | Where every number came from, and how old it is |
| `money.py` | Decimal amounts, Indian numbering, one-way float boundary |
| `ips.py` | Financial DNA → Investment Policy Statement → suitability gate |
| `engine/` | Deterministic finance: returns, risk, allocation, X-ray, tax lots, goals, health, SIP optimiser |
| `ingest/` | CSV, XLSX, PDF and CAMS/KFintech CAS parsing, with exceptions |
| `market/` | Provider-abstracted market data; broker and aggregator connectors |
| `analysis.py` | One deterministic pass → the single source of truth |
| `decisions/` | Named rules → suitability gate → de-duplication → ranking |
| `alerts.py` | Proactive monitoring that stays quiet |
| `reports.py` | Daily brief, weekly report, monthly investment committee |
| `ai/` | Grounded AI banker: gateway, tools, versioned prompts, safety |
| `evals/` | Eleven synthetic investors and an adversarial corpus |
| `crypto.py` | ChaCha20-Poly1305 (RFC 8439) for statements and tokens |
| `store/` | SQLite with a hash-chained audit log |
| `api.py`, `cli.py`, `web/` | HTTP API, command line, generated dashboard |

## The rules that hold it together

**The language model is never the calculator.** `aicio/engine/` is a purity
boundary enforced by a test: no network, no LLM, no clock. Every number a user
sees comes out of it carrying a provenance record.

**Recommending and executing are separate systems.** Nothing in this package
places a trade. Approving a recommendation records an approval.

**A recommendation that cannot argue against itself does not ship.** The domain
model refuses to validate a material action without evidence, risks and
counterarguments.

**Doing nothing is a conclusion, not a fallback.** The `balanced` eval scenario
exists to catch a system that always finds something to say.

## The evals

```
$ python3 -m aicio evals
  adversarial   10/10 (critical)
  calculation    4/4  (critical)
  consistency   11/11
  detection     18/18
  grounding      7/7  (critical)
  no_action      1/1
  schema        11/11
  suitability   11/11 (critical)
  uncertainty    2/2

75/75 passed · OK
```

Four categories fail CI. Failing a build on a judgement call trains people to
skip the suite; failing it on a wrong number is the entire point.

The adversarial cases are the interesting ones. Injected instructions inside an
uploaded statement are stripped and cannot change an answer, and a reply
containing a figure with no fact behind it — or a guarantee, or certainty about
a future price — is replaced rather than shown:

```
I could not answer that safely. My draft contained claims that cannot be made:
a guaranteed return; figures not present in the data: 9,99,99,999. This product
does not show figures it cannot trace to your own data.
```

## Integrations

Zerodha Kite, Upstox, Angel One, RBI Account Aggregator, Plaid, SnapTrade, and a
sandbox connector that follows exactly the same consent rules. Market data from
AMFI (authoritative for Indian mutual funds, keyless) with Yahoo, Finnhub,
Twelve Data and Alpha Vantage behind one interface.

`python3 -m aicio connectors` lists them all with what each still needs. They
register whether or not keys are present, because a connection screen should say
"Zerodha is supported and needs setup" rather than hiding it.

## What is deliberately not built

Execution, regulated advice, autonomy and real-time data — for reasons set out
in [docs/aicio/architecture.md](docs/aicio/architecture.md#6-what-is-deliberately-not-built).
The operating model has to be settled with specialist counsel before launch, and
the product is analytics with disclosures until it is.
