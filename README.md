# carbon-credits

A carbon credit and reforestation project: the research behind it, the
financial model that gates it, and `carbonstack`, the dMRV core it runs on.

## Where things are

| Path | What it is |
|---|---|
| `docs/research/` | Teardown of Mitti Labs and Varaha, and what it implies for us |
| `model/carbon_model.py` | Portfolio cashflow model — the go/no-go gate |
| `src/carbonstack/` | The product — see the map below |
| `src/carbonstack/sites.py` | The two pilot sites — real places, real climatology |
| `src/carbonstack/feed.py` | Simulated monitoring on the real 5-day revisit cadence |
| `dashboard/` | The live MRV dashboard and its dataset |
| `tests/` | 140 tests, stdlib only |

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
