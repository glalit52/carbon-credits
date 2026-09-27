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
| `dashboard/` | The live MRV dashboard, its dataset and example evidence packs |
| `scripts/` | Build the dashboard dataset and page |
| `tests/` | 294 tests, stdlib only |

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
python -m pytest                         # 294 tests

python -m carbonstack demo               # both tracks against synthetic monitoring
python -m carbonstack export estate --out project.json
python -m carbonstack eligibility project.json
python -m carbonstack quantify project.json --year 2031 --methodology VM0047
python -m carbonstack explain  project.json --year 2031
```

### What it does

**Quantifies credits under four methodologies.** `VM0047` (afforestation,
reforestation, revegetation) credits growth net of a dynamic performance
benchmark, exactly as the methodology requires: the baseline is re-derived at
each verification from what comparable land actually did, not argued once in a
project document. It ships both approaches — area-based off a stocking index,
and census-based off counted stems, which is the only one that works over
scattered trees. `VM0051` (improved rice management) credits avoided methane
against a measured baseline water regime. `VM0042` (improved agricultural land
management) credits practice adoption times an emission factor, and its soil
pathway credits measured SOC change under `VMD0053`.

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
  sar.py            Sentinel-1 backscatter, water-regime detection, scoring
  methodology/      VM0051 (rice), VM0047 (ARR, area-based + census), VM0042 (cropland + soil)
  agroforestry.py   species allometry, survival surveys, census inventory
  stacking.py       pillar claims per plot, and the double-counting engine
  soil.py           SOC stocks, equivalent soil mass, sampling, VMD0053
  article6.py       host-country authorisation, corresponding adjustments
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

## Methodology review, and what it changed

Four independent reviews of this prototype came back in September 2026. They
agreed on findings that are now implemented, and the first one says the
prototype was wrong.

### Rice belongs under VM0051, not VM0042

VM0042 covers rice, but it is an agricultural land management methodology.
**VM0051** is written for rice, replaces CDM AMS-III.AU in the VCS Program, and
is CORSIA eligible. Three things follow, and each changes an answer:

| | VM0042 (what the prototype did) | VM0051 (what it does now) |
|---|---|---|
| Eligibility | any cropland | irrigated lowland rice only — upland, rainfed and deepwater excluded |
| Additionality | not tested | fails if AWD penetration in the jurisdiction is already common practice |
| Buffer pool | 15% withheld | **none** |

The buffer is the practical one. Non-permanence applies to carbon held in a
stock that can be released; avoided methane was never stored, so it cannot
reverse. On the Vallam pilot that difference alone takes the 2025 vintage from
1 issuable credit to 2.

Eligibility is now a gate rather than a note: Verra rejected a run of rice
projects in 2025 for insufficient additionality evidence, so a field whose
water regime or drainage control is unrecorded is excluded rather than assumed
creditable.

### Stacking partitions by carbon pool, not by activity

The differentiator and the biggest audit risk are the same fact. The rule is
not obvious: **VM0042 credits soil carbon *and* rice methane**. So a paddy
hectare cannot carry VM0051 methane beside a VM0042 soil claim — the methane
would be sold twice, even though the two sound like different products.

`stacking.py` refuses that shape at registration rather than at verification:

```
$ carbonstack stack add IN-TNJ-01 IN-TNJ-01-P1 --pillar soil_carbon     --methodology VM0042 --area 0.2 --actor lalit
refused: cannot stack soil_carbon on IN-TNJ-01-P1:
  VM0051 (methane) and VM0042 (soil_carbon) both credit ch4_avoided on the
  same plot -- the same tonne would be sold twice
```

Trees stack cleanly with either, because biomass is a pool neither touches —
but only on **separate geometry**, since a bund planted with trees is not also
growing rice. `carbonstack stack audit` is the evidence that no hectare is
claimed twice, and it ships in the evidence pack.

### Records a registry asks for that the product had no room for

Each of these blocked validation and is now enforced:

- **Carbon rights, not just data consent.** Permission to use a farmer's data
  is not the right to sell their carbon. Enrolment now captures the agreement,
  the holder, and the farmer's acknowledgement of the reversal clause.
- **Baseline before practice change.** A farmer already practising AWD has no
  counterfactual left to measure. The eligible pool shrinks every season this
  goes uncaptured, so the timing is checked and flagged.
- **Stakeholder consultation and a grievance channel.** Required by Verra and
  Gold Standard both. A project can be scientifically perfect and still fail on
  this.
- **Methodology version pinned per project.** VM0042 v2.2 took corrections in
  June 2026 with a major revision in progress; a number that does not say which
  version produced it cannot be reproduced.

These are reported apart from per-plot findings when they block the whole
project at once, so they do not bury the rest.

### Cost per issued tonne replaces cost per verified hectare

A cheap hectare carrying a large uncertainty deduction issues few credits and
is a worse business than a dearer one that issues many. The dashboard and the
portfolio model both now report the metric that is actually managed:

| | Revenue / issued t | Cost / issued t | Margin |
|---|---|---|---|
| Vallam paddy | $12.00 | $39.19 | **−$27.19** |
| Gatugi coffee | $26.00 | $16.91 | **+$9.09** |

The same finding as before, stated in the unit that decides it.

## The soil pathway (VMD0053)

Soil is the one pillar whose numbers cannot come from a satellite. VM0042
requires physical cores, an accredited lab, an equivalent-soil-mass
correction, and — where a model quantifies between samplings — calibration and
validation under **VMD0053**.

```bash
carbonstack soil design --strata "clay loam:320:9.5,sandy loam:180:14,saline:40:6"
carbonstack soil ingest   IN-TNJ-01 lab.csv        --actor field
carbonstack soil validate IN-TNJ-01 val.csv --model DayCent --version 2026.1 --actor science
carbonstack soil quantify IN-TNJ-01 --year 2028    --actor lalit
carbonstack soil status   IN-TNJ-01
```

### Compaction is not sequestration

Compare SOC over a fixed **depth** and a field that was merely rolled looks
like it gained carbon — the same 30 cm now holds more soil, so it holds more
carbon, and nothing was sequestered. Equivalent soil mass compares a fixed
**mass** of fine earth instead. On a real pair of cores the difference is the
whole answer:

```
fixed depth change : +0.10 t C/ha  <- looks like a gain
ESM change         : -2.10 t C/ha  <- the truth
compaction artefact: +2.20 t C/ha
```

The engine refuses to report a fixed-depth change, and flags the bulk-density
movement on the vintage so a reviewer sees it.

### Sample deeper than you compare

This falls out of ESM and is the most common way a soil project discovers,
years later, that its cores cannot be compared at all. Good management
*loosens* soil, so a monitoring core taken to the comparison depth holds
**less** mass than the baseline did, and the reference mass becomes
unreachable. A core cannot be extended after the fact, so the headroom has to
be designed in from the first sampling:

```
! sample to 40 cm, not 30 cm: equivalent soil mass needs headroom if bulk
  density falls, and a core cannot be extended after the fact
```

Extrapolating past the bottom of a core is refused rather than guessed.

### A model nobody validated is not evidence

VMD0053 asks for goodness of fit and a characterised prediction error, and
that error becomes the uncertainty deduction. So a poorly validated model does
not fail quietly — it costs credits. The same measured carbon, twice:

| | Relative uncertainty | Net issuable |
|---|---|---|
| DayCent 2026.1, held-out validation | 5.7% | **46.6 tCO2e** |
| No validation on record | 75% (punitive default) | **18.6 tCO2e** |

Validating the model is worth **2.5×** on identical cores. Three things are
refused outright: a model scored on its own training data, fewer than ten
validation pairs, and an unversioned model. Bias is *added* to RMSE rather
than averaged with it, because a systematic offset does not cancel across
plots the way scatter does.

### Sampling design

Stratified random sampling with Neyman allocation — cores go where the
variance and the area are, not evenly, because cores dominate the cost of a
soil project. Every stratum gets a floor of three, since one or two cores have
no usable variance whatever the formula says.

### Soil carries a buffer, unlike avoided methane

Soil carbon is a stock and a single tillage pass can release it, so the
non-permanence buffer applies at 15%. That is exactly the difference from
VM0051, where avoided methane was never stored and cannot reverse.

## Article 6: who is allowed to count the tonne

A different question from how many there are, and getting it wrong does not
produce a bad number — it produces a buyer telling their regulator something
untrue.

```bash
carbonstack article6 authorise IN-TNJ-01 --authority "MoEFCC, Government of India"     --reference MoEFCC/A6/2026/0041 --issued-on 2026-03-01 --use corsia     --volume 50000 --first-vintage 2025 --last-vintage 2030 --actor legal
carbonstack article6 adjust <auth-id> --year 2025 --volume 2     --applied-on 2026-06-30 --reported-in "India BTR 2026, Annex 6.2" --actor legal
carbonstack article6 claims IN-TNJ-01
```

Three claims are routinely conflated and only one needs a corresponding
adjustment:

| Basis | What the buyer may say |
|---|---|
| **Unadjusted voluntary** | *financed* the reduction — India still counts the tonne toward its NDC |
| **Authorised ITMO** | offset against their own target — India has adjusted its account |
| **CCTS domestic** | an Indian Carbon Credit Certificate, not for international transfer |

### A letter is a promise; an adjustment is the promise kept

The gap between them is where double claiming actually lives, so the two are
separate records and only the **adjusted** portion is offsettable:

```
vintage 2025  [authorised_itmo]
  issued 2.00  offsettable 0.00  unadjusted 2.00
  authorised for transfer, but NO corresponding adjustment has been applied
  yet; until it is, these tonnes may NOT be counted against the buyer's own target
```

That buyer-facing line is derived from the adjusted volume, not from the basis
— an authorisation with nothing behind it is still an ITMO *by basis*, and a
reader who saw only "offset against your target" would make a false claim.
A partial adjustment splits the statement rather than rounding it up.

Also enforced: CORSIA eligibility needs an authorisation that names CORSIA
*and* an applied adjustment; a revoked or expired authorisation says so by
name and date rather than vanishing into "none on record"; adjustments beyond
the authorised volume are flagged; and a project registered under both CCTS
and an international authorisation is told to confirm the CCTS certificates
were cancelled or never issued, because the code cannot see that registry.

`claim_register.json` ships in the evidence pack — it is the page a buyer's
counsel reads before signing and the one a CORSIA auditor asks for.

## Agroforestry: count the trees, do not infer them

The pathway the project leads with, and the one where the instrument choice
changes the answer by more than any deduction does.

`VM0047` ships two approaches and they are not interchangeable. The
**area-based** approach reads a stocking index off the canopy. It works over a
contiguous block. It fails completely over the planting most smallholder
agroforestry actually is: a line of trees on a paddy bund is narrower than a
10 m Sentinel-2 pixel, and an index that returns near zero over a thriving
bund line is not a conservative estimate, it is a wrong one. So the
**census-based** approach counts.

```bash
carbonstack trees species                                  # the allometry catalogue
carbonstack trees ingest KE-NYR-01 field.csv --actor lalit # one row per measured stem
carbonstack trees survival KE-NYR-01                       # what is credited, and why less
carbonstack trees quantify KE-NYR-01 --year 2027 --actor lalit
carbonstack trees status KE-NYR-01
```

### Planted is not established

A survival rate asserted from the planting record is the easiest thing in an
ARR project for a verifier to reject. Survival here is a sample with an
interval, and the **lower bound** is what gets credited:

```
plot            visited       planted  sampled  alive    rate  credited
KE-NYR-01-P1    2027-11-20        340       40     35     88%       269
```

269, not 298. The point estimate would claim thirty trees the surveyor did not
find. The binomial standard error carries a finite population correction, so a
census of every stem is charged no sampling error at all — the deduction
tracks uncertainty that was actually incurred. Below **70% survival** a plot is
excluded from the vintage and flagged for replanting rather than credited at a
reduced rate: a failing planting needs replacing, not a smaller cheque.

### Three error sources, added in quadrature

Stem sampling error (forty stems standing for three hundred), allometric error,
and survival sampling error are independent, so they combine in quadrature
rather than summing — and all three reach the uncertainty deduction instead of
a footnote. Chave et al. (2014) pantropical form is implemented because a
verifier recognises it:

```
AGB(kg) = 0.0673 × (ρ · D² · H)^0.976
```

alongside per-species power laws on diameter or height alone. Height-only is
deliberately the weakest and widest: measuring from the air is cheaper, and the
methodology charges for it. Every species in the catalogue is a placeholder
until a local fit replaces it, and `is_locally_calibrated` says so in the CLI,
the API and the evidence pack. The allometry is **stored with the
measurements**, so a local fit that lands next year cannot silently restate
last year's inventory at a new number.

### The two instruments disagree by 5x, and that is the finding

Gatugi is shade coffee, so the upper canopy really is the shade trees and both
approaches are legitimate there. Running both over the same trees is the only
honest way to show what the census costs:

| Vintage | Area-based tCO2e | Census tCO2e |
|---|---|---|
| 2029 | 47.6 | 6.7 |
| 2030 | 54.8 | 10.0 |
| 2031 | 57.2 | 11.4 |

The area-based path credits about **5.4x** what the census does. Its stand fit
assumes a closed canopy; at 100 stems/ha this block does not have one, so
canopy height is reading coffee and gaps as forest. The census is the floor,
and the economics on this site — which run off the area-based path — are
optimistic by roughly that factor. The dashboard states this on the page
rather than in a footnote, because a number nobody reconciled is how a project
gets to validation before finding out.

### What the census pathway refuses

* Crediting the survival point estimate instead of the lower bound.
* Issuing against an unvetted performance benchmark. A benchmark nobody vetted
  turns every project into a high performer.
* Crediting a plot that has no census. A census credits what was counted; a
  plot without one contributes nothing rather than inheriting a neighbour's
  average.
* Storing a survival survey with no surveyor, for the same reason a soil core
  with no lab reference is refused — an unattributable measurement is not
  evidence, and storing it invites it into a claim later.

`tree_inventory.csv` ships in the evidence pack: who walked the plot, how many
stems they checked, which equation priced them, and what the uncertainty was.

## Rice methane: detecting the dry-down, not asserting it

The rice pathway credits avoided methane, and methane is avoided when the
paddy is not flooded. The whole claim rests on one observable — the water
state of the field, several times a season, for every plot — and until now
the product asserted it. The simulator knew whether a dry-down had happened
and handed that straight to the confidence term. Nothing detected anything.

```bash
carbonstack rice regime vallam                       # season by season
carbonstack rice passes vallam --year 2026 --season Kuruvai
carbonstack rice validate vallam                     # score it against truth
```

### Why radar, and why it is harder than it looks

**Cloud.** AWD is practised in the monsoon. Thanjavur's Samba season runs
through the north-east monsoon and optical passes are lost exactly when the
evidence matters — 60–67% usable against radar's 62–76%. C-band SAR does not
care about cloud, and Sentinel-1 gives a 6-day revisit.

**And then the signal inverts.** A *bare* flooded field is a mirror: it
scatters the pulse away and comes back dark, around −19 dB. A flooded field
with a rice canopy is **bright** — the stems and the water surface form a
dihedral and the pulse comes back twice. So VV over flooded paddy climbs past
a drained field's response by mid-season:

```
stage 0.0    flooded −19.0 dB   drained −12.5 dB    flooded is 6.5 dB darker
stage 0.54   flooded −12.0 dB   drained −12.0 dB    no information at all
stage 1.0    flooded  −6.0 dB   drained −11.5 dB    flooded is 5.5 dB brighter
```

A fixed threshold — which is how most published flood maps work — is right in
June and inverted in September. `WaterRegimeDetector` estimates crop stage
from VH, which tracks canopy volume and barely moves with what is underneath,
then compares VV against what each state would produce *at that stage*.

### It abstains

Around the crossover the two states are separated by less than the speckle.
There is no information there, so the detector returns AMBIGUOUS rather than a
coin flip dressed up as a measurement. Roughly 30% of passes land there, and
that shows up as coverage rather than as confident nonsense.

An unreadable pass between two passes that **agree** — and that are within
1.8 dB of it — is carried across, marked as inferred and discounted to 60% of
a call the radar actually resolved. A gap between passes that *disagree* is
never filled: the transition is exactly what must not be invented, because an
AWD event conjured out of an unreadable pass is the failure this module
exists to prevent.

### The harvest drain is not an AWD event

Every paddy is drained before harvest — in the project and in the baseline
alike — so counting it would credit the counterfactual. The detector has no
crop calendar; it has the canopy stage it estimated from VH, which rises to a
peak and falls as the crop senesces. A spell that begins after that peak and
runs to the last pass of the season is the harvest drain, and it is excluded
by name:

```
dry 2026-09-18 to 2026-09-24   12 d  2 pass(es)  harvest drain
```

### What it recovered

Scored against the water state the simulator actually used, which the
detector never sees:

| | |
|---|---|
| Passes | 158 |
| Called | 75 |
| Abstained | 33 (not separable at their crop stage) |
| Accuracy | 96.0% |
| Precision, flooded | 100% |
| Called dry when flooded | 3 — *the error that over-credits* |
| Called flooded when dry | 0 |

### Measuring costs credits, and that is the point

| Vintage | Asserted | Detected |
|---|---|---|
| 2025 | 88% | 71% |
| 2026 | 54% | 51% |
| 2027 | 86% | 61% |

Detection is more conservative everywhere, because a third of the passes
cannot be read and short drainages seen by a single unclean pass do not
count. The 2025 vintage falls from 1.376 to 1.114 tCO2e net — 19% of the
claim. On a 2.49 ha plot that is still one whole credit either way; across a
programme it is the difference between a margin and a rounding error. It is
also the honest number, and the derivation now carries the passes it came
from:

```
detected water regime, Kuruvai + Samba 2025
  passes in season          37 acquisitions
  usable passes             26 acquisitions   11 not separable at their crop stage
  coverage              0.7027 fraction
  qualifying dry spells      4 events         runs of >= 6 days
  ==========================================  0.7126 confidence
```

The lapsed season is found without being told about it: `2026 Kuruvai`
detects zero AWD events, scores 25%, and raises *"Kuruvai scored 25% on its
own; the year is carried by the other season and this one needs review"* —
because a year rolled up by baseline exposure must not average a failed season
into silence.

Also enforced: a season that wraps the new year (Samba runs August to January)
cannot be verified on 31 December, and a vintage quantified early says which
season was still open. `vv_db` and `vh_db` are stored as observations like any
other measurement, and `water_regime.csv` in the evidence pack rebuilds every
call from the database alone — if the stored observations cannot reproduce the
call, the call is not evidence.

## What is deliberately not real yet

Four placeholders are marked in the source and must be replaced before any
issuance. They are project milestones, not refinements:

1. **The allometric equation.** A generic stand fit at 25% error. Replace with
   a locally calibrated equation — this is the tree-project equivalent of a
   Tier 3 emission factor, and the tests show what it is worth.
2. **The performance benchmark.** Currently a constant. Replace with a
   Verra-vetted data service provider over a matched control population. A
   benchmark set near zero turns every project into a high performer, which is
   the failure mode VM0047 exists to close.
3. **The monitoring provider.** `SyntheticProvider` is deterministic fiction
   that proves the pipeline, and `sar.simulate_pass` renders a hidden water
   state as backscatter. The detector that reads it is real and is scored;
   the granules it reads are not. The real source is Sentinel-2 optical plus
   Sentinel-1 SAR fused with GEDI spaceborne LiDAR, which drops into the same
   `Provider` interface without touching quantification.
4. **Detector validation.** The 96% accuracy above is against a simulation.
   Real validation needs field water-level loggers on a sample of plots,
   which is what VM0051 expects and what that number stands in for.

Emission factors for cropland practices are likewise conservative placeholders
carrying Tier 1 uncertainty, which the engine already charges for.

## Open question

Reforestation is unfinanceable without provable long-horizon land rights, and
`eligibility` is built to enforce that. Which landscape, how many hectares,
and what tenure evidence exists is the input nothing else can substitute for.
