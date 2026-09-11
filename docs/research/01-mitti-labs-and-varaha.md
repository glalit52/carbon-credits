# Teardown: Mitti Labs and Varaha

**Status:** research note, September 2026
**Purpose:** understand how the two most successful India-based carbon project
developers actually work, before we commit to a design for our own carbon
credit + reforestation project.

Everything here is from public sources (listed at the bottom). Numbers from
press coverage are marked where they could not be confirmed against a registry
or a company filing. Treat single-source figures as directional.

---

## 0. Why these two, and what they are *not*

Both are Indian, both sell to the same buyer set, and both raised serious money
in the last 18 months — but they are structurally different businesses, and the
difference is the most useful thing in this document.

| | **Mitti Labs** | **Varaha** |
|---|---|---|
| Founded | 2023 | 2022 |
| Core bet | One pathway, done deeper than anyone | Many pathways, one platform |
| Credit type | **Avoidance** (methane not emitted) | **Removal** (carbon put somewhere) |
| Pathway | Rice methane via Alternate Wetting & Drying (AWD) | Regen ag, biochar, enhanced rock weathering (ERW), agroforestry/ARR |
| Registry | Gold Standard | Verra (VM0042), Puro.earth, Isometric |
| Anchor buyer | Google — 1M credits through 2030 | Google — 100k t biochar; Mirova — $30.5M |
| Disclosed funding | ~$12.5M total ($9.5M Series A, Aramco Ventures lead) | ~$50M+ ($20M equity; $30.5M Mirova, structured as credit prepay not equity) |
| Reported scale | ~100k ha at peak across KA/AP/TS | 200k+ farmers; 14 projects; ~150k credits issued |

Neither is a reforestation company. That matters: **the thing we say we want to
build (reforestation) is the pathway neither of them chose to lead with**, and
their reasons for that are the single most important input to our own plan.
Section 5 deals with this directly.

---

## 1. Mitti Labs — depth in one pathway

### The physical mechanism

Flooded rice paddies are anaerobic. Anaerobic soil breeds methanogens. Rice
cultivation is one of the largest anthropogenic methane sources on earth.
Alternate Wetting and Drying (AWD) is the intervention: let the field dry down
to a set depth before re-flooding, several times per season. Oxygen enters the
soil, methanogenesis collapses.

Reported effect: **~50% methane reduction and ~40% less irrigation water, with
no yield penalty.** The no-yield-penalty part is what makes farmer adoption
possible at all — and the water saving is arguably a stronger adoption lever in
water-stressed districts than the carbon payment is.

Methane is ~28x CO2 over 100 years, so a hectare of rice throws off a
respectable credit volume for a change in *water scheduling*. No planting, no
new asset, no 20-year commitment. Compare that to a tree.

### Why the credits are worth something

The hard part of rice methane is not the agronomy, it is proving the practice
happened on land you never visited. Their answer is a dMRV stack that detects
flood/dry cycles, seeding and harvest from remote sensing across thousands of
smallholder plots.

Two claims are doing the real work commercially:

1. **Tier 3 emission factors.** IPCC accounting has tiers. Tier 1 is a global
   default number out of a table. Tier 2 uses country/region-specific factors.
   Tier 3 is model- or measurement-based, specific to local conditions. Mitti
   builds Tier 3 factors from direct methane flux measurement and field trials
   in their own geographies. They received a Tier 3 issuance from Gold Standard
   (June 2026) — the first credits under this approach.
2. **Census, not sample.** Conventional verification for smallholder ag reviews
   farmer logbooks and interviews for a sample — they cite under 1% of farmers
   getting reviewed. Mitti monitors every acre remotely.

Those two together are the whole product thesis: *a buyer is not paying for
methane avoidance, they are paying for methane avoidance they will not be
embarrassed by in three years.* Tier 3 + census-level monitoring is what
justifies the price and what got Google to commit at volume.

### The commercial shape

- Google agreed to buy **1 million credits through 2030** — reportedly the
  largest publicly announced rice-methane deal to date (Sept 2026).
- Geography: Karnataka, Andhra Pradesh, Telangana. ~100,000 ha at peak delivery.
- Farmers are paid to adopt the practice — the payment is the adoption lever,
  the credit is the financing.
- $9.5M Series A led by Aramco Ventures, with Lightspeed India, Godrej
  Industries Group, Cisco Foundation, Francis Family Fund, Volta Circle.
  Total ~$12.5M since 2023. Notably positioned as **water resilience**, not
  only carbon — that framing widens the funder set beyond carbon buyers.

### What is replicable and what is not

Replicable: the dMRV-first posture, the census-monitoring argument, the
single-pathway focus, the co-benefit framing (water).

Not replicable cheaply: **Tier 3 emission factors are a multi-year, capital-
intensive science asset.** Direct flux measurement campaigns, field trials,
peer-reviewable model development. That is the moat, and it is the reason a
2023-founded company could sign a landmark deal in 2026 — they spent the
intervening time building measurement infrastructure, not sales decks.

---

## 2. Varaha — a platform across pathways

### The thesis

Varaha's bet is the inverse: build one dMRV + farmer-operations platform, then
run whatever carbon pathway the science and the market currently reward. They
now describe themselves as the largest carbon project developer in Asia, across
South Asia and Africa.

Portfolio as of 2026:

- **Regenerative agriculture** (Verra VM0042) — direct-seeded rice, crop-residue
  management, reduced tillage, soil health. This is the flagship *Kheti*
  programme.
- **Biochar** (Puro.earth) — notably converting *Prosopis juliflora*, an invasive
  species, into biochar in Banni, Gujarat. Invasive-species feedstock is elegant:
  the removal and the biodiversity restoration are the same act.
- **Enhanced rock weathering** (Puro.earth) — basalt powder on smallholder cotton
  farms, scaled to 100,000 t of basalt. **Asia's first registry-backed ERW
  issuance**, third in the world. They are the first company anywhere with
  verified issuances across two distinct CDR pathways (ERW + biochar).
- **Agroforestry / ARR** — e.g. an Andhra Pradesh agroforestry project.

### The technology

- **Vann** — a field-operations and dMRV mobile app, including a dedicated ARR
  variant. This is the ground-truth layer: enrollment, plot boundaries, practice
  evidence, photos, geotags.
- **Carbon Quantification Tool (CQT)** — in-house GHG quantification engine for
  partner enrollment, measurement, reporting and verification at scale.
- Remote sensing + geospatial + ML on top, with AI-driven quality control.
- They describe a **"zero-trust" dMRV posture**: continuous AI and satellite
  verification, near-daily, replacing periodic manual audit.

The interesting design decision is app-plus-satellite rather than satellite-only.
For soil carbon and agroforestry you cannot see the practice from orbit reliably
enough — you need a human with a phone at the plot, and then you use satellite
to *catch* the human. That is a different architecture from Mitti's, and it is
driven by pathway, not by taste.

### The commercial shape

- **Google**: 100,000 tonnes of biochar removal credits.
- **Mirova**: $30.5M — and the structure matters more than the number. Mirova
  did **not take equity**; it put in cash and receives a share of the credits
  generated over time. This is a **credit prepay / streaming deal**, the same
  instrument mining uses. It finances working capital without dilution and
  transfers delivery risk to the developer.
- **$20M equity** round (Feb 2026) to scale carbon removal from the Global South.
- Reported impact: >2 million tonnes CO2 addressed across 14 active projects,
  ~150,000 removal credits generated. (Note the gap between "addressed" and
  "issued" — always read these two numbers separately.)
- Registry-agnostic by policy: Verra for soil because they judge it the most
  advanced soil-carbon science, Puro and Isometric for engineered removals.

### What is replicable and what is not

Replicable: registry-agnosticism, the app-plus-satellite architecture, the
invasive-feedstock idea, the prepay financing structure.

Hard: **Varaha's moat is operational, not scientific.** Enrolling 200,000+
smallholders, holding boundary and consent data clean enough to survive audit,
and running field teams across states and countries is a logistics company
wearing a climate-tech logo. That is years of unglamorous work and it does not
compress with funding alone.

---

## 3. Seven patterns worth stealing

1. **Sell the verification, not the carbon.** Both companies' pitch is
   fundamentally about MRV credibility. Credits are a commodity; trust is not.
   Google bought both times because the measurement story held.
2. **Pick pathways with a short evidence loop.** Rice methane credits within a
   season. Biochar credits on production. ERW on application plus weathering.
   All fast. Trees take 5–10 years to credit meaningfully. This is why neither
   led with reforestation.
3. **The co-benefit is the adoption lever.** Farmers adopt AWD for water and
   yield stability; carbon is the financing mechanism behind the scenes. A
   project whose only story is carbon has a farmer-retention problem.
4. **Anchor offtake before scale.** Google-shaped offtake converts a science
   project into a financeable asset. Get the LOI/offtake conversation started
   before the hectares, not after.
5. **Non-dilutive credit prepay is available.** Mirova's structure is the
   template — capital against future credits, no equity.
6. **Registry choice is a per-pathway decision.** Gold Standard for rice
   methane, Verra VM0042 for soil, Puro for biochar/ERW, Isometric for novel
   removals. Do not marry a registry.
7. **Own the ground-truth layer.** Both built their own field app. Nobody's
   dMRV survives audit on satellites alone for land-based pathways.

---

## 4. Economics reality check

This is the part that kills most projects, so it goes in early.

Reported figures for smallholder soil-carbon programmes:

- Inputs and training: **~$150 per farmer**
- MRV: **~$150–200 per farmer**
- A smallholder sequestering **1–3 tCO2e/yr** at **$5–15/credit** earns
  **$5–45/yr**

That is a structurally broken unit economic at small scale. The fixes the
industry actually uses:

- **Aggregate hard.** Minimum viable clusters cited at ~50 farmers / 200–500 ha;
  real projects run in the tens of thousands of farmers. Aggregators typically
  take **30–60%** of credit revenue to cover fixed costs.
- **Drive MRV cost down with remote sensing** — this is exactly Mitti's and
  Varaha's core investment, not a nice-to-have.
- **Pick a higher-value credit.** Price ranges as of 2026:

| Credit type | Indicative 2026 price |
|---|---|
| ARR / reforestation (average) | ~$22/t |
| ARR, low-rated | ~€9/t |
| ARR, BBB+ rated | ~€28.55/t |
| Biochar, India artisanal | ~€105/t |
| Biochar, India industrial | ~€120–150/t |
| Biochar/ERW via Puro / Carbonfuture | $200–400/t |

Read that table twice. **A well-rated ARR credit earns ~3x a poorly-rated one
for the same trees** — quality rating is not a vanity metric, it is the revenue
line. And durable removals (biochar, ERW) clear at 5–15x nature-based avoidance.

Indian domestic registry fees, for reference: ₹25,000 account registration,
₹20,000 project listing, ₹5/credit for the first million.

Common revenue-share shape cited for Indian agroforestry: 60% farmer, 25%
developer, 15% maintenance/monitoring.

---

## 5. What this means for reforestation specifically

If we want to do reforestation, the governing document is **Verra VM0047**
(Afforestation, Reforestation and Revegetation, v1.1, June 2025), now
**ICVCM CCP-approved** — meaning credits under it can carry the Core Carbon
Principle label, which is what separates the €28 credit from the €9 one.

What is genuinely new about VM0047, and why it changes our build:

- It is the **first nature-based methodology to use remote sensing for dynamic
  performance benchmarks and additionality testing.** Instead of arguing about
  a counterfactual in a PDD, the baseline is re-derived from observed data at
  each verification.
- The **stocking index (SI)** is the central measured quantity. Verra has vetted
  external **Data Service Providers** (Sylvera among them) to supply SI data for
  benchmarks.
- Remote sensing is explicitly allowed for historical land cover assessment,
  burned-area monitoring, and SI calculation/monitoring.
- Two crediting approaches exist (area-based and census-based) — which one we
  pick is a real design decision, not a formality.

**The honest problem with reforestation as a first project:**

| Factor | Rice methane / biochar | Reforestation (ARR) |
|---|---|---|
| Time to first credit | Months to ~1 season | Typically 5+ years |
| Capital before revenue | Low | High and sustained |
| Permanence obligation | Limited / n/a | 30–100 yr, buffer pool deductions |
| Land tenure requirement | Weak | **Strong — must prove long-horizon rights** |
| Price realised | €105–400/t (durable) | ~$22/t average |
| Reversal risk | Low | Fire, grazing, felling, drought |

Reforestation is the *slowest, most capital-hungry, lowest-priced-per-tonne,
highest-reversal-risk* pathway on the board. That is not an argument against
doing it. It is an argument against doing it **first, alone, and unfunded**.

The pattern that works — and it is Varaha's — is: **run a fast-cycle pathway to
generate cashflow and MRV credibility, and let it carry the reforestation
project through its pre-credit years.** Agroforestry is the natural bridge,
because it puts trees on farmland already enrolled for soil carbon, so the
enrollment, boundary data, farmer relationship and field app are already paid
for by the other pathway.

---

## 6. Risks and known failure modes

Documented, not hypothetical:

- **Over-crediting / MRV collapse.** Northern Rangelands Trust (Kenya) credits
  were suspended over flawed soil-carbon accounting. Soil carbon measurement at
  scale is genuinely hard and the market now knows it.
- **Registration attrition.** Of agriculture projects listed with Verra in
  India, only a fraction have registered and — per the source — none had issued
  credits. Listing is not registration; registration is not issuance. Model our
  plan on issuance.
- **Farmer follow-through.** Projects fail on poor extension services and weak
  follow-up, especially with marginalised communities. 85%+ of Indian farmers
  are smallholders with no prior exposure to carbon crediting.
- **Permanence and reversal.** Unresolved for smallholder land. Buffer pool
  contributions reduce sellable volume from day one.
- **Double counting / corresponding adjustments.** With India's CCTS live, the
  interaction between voluntary credits and the national mechanism is a live
  legal question, not a settled one.

**Policy context we must design around:** India's **CCTS** launches mid-2026,
replacing PAT with a GHG-intensity trading scheme. Its **offset mechanism** for
non-obligated sectors (agriculture, forestry) is being operationalised, the
Indian Carbon Market Portal launched March 2026, and eight BEE-approved offset
methodologies exist so far — including **mangrove afforestation/reforestation**.
Critically: **projects must have a start date no earlier than 1 January 2025.**
That is a hard eligibility gate and it is in our favour if we start now.

---

## 7. Decisions we need to make before writing any code

These are genuinely open and they change what gets built:

1. **Are we a project developer (we own the credits and the farmer
   relationships) or an MRV software vendor (we sell the stack to developers)?**
   Mitti and Varaha are both developers who built software. The reverse business
   is a different company with different margins and a much smaller TAM today.
2. **Which pathway funds year 1–4?** Reforestation alone does not.
3. **Voluntary (Verra/Gold Standard/Puro) or India CCTS, or both?** Different
   methodologies, different buyers, different price points, potential conflict.
4. **What land do we actually have access to, and what tenure evidence exists?**
   ARR is unfinanceable without this. This is the fastest way to disqualify a
   plan, so it should be checked first.
5. **Do we build ground-truth capture (a Vann equivalent) or buy it?**
6. **What is our defensible measurement asset** — the Tier 3 equivalent? Without
   one we are reselling commodity satellite indices.

---

## 8. Proposed next steps

Sequenced so that the cheap disqualifying checks happen first.

**Phase 0 — Decide (this week).** Answer the six questions in §7. Nothing below
is worth starting until §7.1, §7.2 and §7.4 have answers.

**Phase 1 — Feasibility, desk-only (2–4 weeks).**
- Read VM0047 v1.1 in full, plus the CCTS offset methodology list, and write a
  one-page eligibility memo for a specific candidate landscape.
- Build a bottom-up financial model for that landscape: hectares, species,
  growth curves, credit timing, buffer deduction, MRV cost/ha, farmer share.
  Kill the plan here if it does not clear.
- Map the ground-truth data we would need and what already exists.

**Phase 2 — Prototype the MRV core (4–8 weeks).**
The technically interesting and reusable piece, and the only part that is
software: a stocking-index / biomass pipeline over a real AOI. The literature
converges on a known-good architecture — **Sentinel-2 optical (plus Sentinel-1
SAR) fused with GEDI spaceborne LiDAR as sparse height/biomass ground truth, ML
model on top, with explicit uncertainty quantification.** Open global canopy
height models and code exist to benchmark against. Deliverable: canopy
height + biomass + uncertainty for one candidate site, validated against
whatever field plots we can get.

**Phase 3 — Pilot.** One cluster, real farmers, real enrollment, ground-truth
app, one verification cycle. Small enough to fail cheaply.

Running throughout: **start the offtake conversation early** (Phase 1, not
Phase 3), and explore credit-prepay financing on the Mirova model rather than
assuming equity.

---

## Sources

Mitti Labs:
- [Google signs its biggest rice-methane carbon credit deal with Mitti Labs — TechCrunch](https://techcrunch.com/2026/09/10/google-signs-its-biggest-rice-methane-carbon-credit-deal-with-indian-startup-mitti-labs/)
- [Mitti Labs](https://www.mittilabs.earth/)
- [Tier 3 issuance from Gold Standard — Mitti Labs](https://www.mittilabs.earth/insights/gold-standard)
- [Mitti Labs raises $9.5M Series A — pulse2](https://pulse2.com/mitti-labs-raises-9-5-million-series-a-to-expand-geoai-platform-across-asias-rice-fields/)
- [Mitti Labs raises $9.5M to build water resilience — PR Newswire](https://www.prnewswire.com/in/news-releases/mitti-labs-raises-9-5-million-to-build-water-resilience-in-asias-rice-fields-302843639.html)
- [Google & Mitti Labs partner across India's rice fields — PR Newswire](https://www.prnewswire.com/news-releases/google--mitti-labs-partner-to-eliminate-methane-and-scale-climate-smart-ag-practices-across-indias-rice-fields-302873982.html)
- [Alternate Wetting and Drying (AWD) — Sylvera](https://www.sylvera.com/blog/alternate-wetting-and-drying-awd-tech-rice-cultivation-climate-impact)
- [New methodology to curb methane emissions in rice — Gold Standard](https://www.goldstandard.org/news/new-methodology-to-slash-methane-emissions-from-rice-cultivation-and-empower-smallholder-farmers)

Varaha:
- [Varaha](https://www.varaha.earth/)
- [Varaha signs landmark deal with Google — AgFunderNews](https://agfundernews.com/breaking-varaha-signs-landmark-deal-with-google-to-make-smallholders-part-of-the-carbon-removal-solution)
- [Mirova pours $30.5M into Varaha — TechCrunch](https://techcrunch.com/2025/11/12/kering-backed-fund-mirova-pours-30-5m-into-indias-varaha-for-regenerative-farming-push/)
- [Varaha bags $20M to scale carbon removal from the Global South — TechCrunch](https://techcrunch.com/2026/02/03/indias-varaha-bags-20m-to-scale-carbon-removal-from-the-global-south/)
- [Varaha issues first registry-backed ERW carbon credits in Asia — Carbon Herald](https://carbonherald.com/varaha-issues-the-first-registry-backed-erw-carbon-credits-in-asia/)
- [Varaha CEO on carbon removal projects — ESG Dive](https://www.esgdive.com/news/varaha-ceo-talks-carbon-removal-projects-climate-tech-and-sustainable-agri-mirova-google-biochar-erw/806192/)
- [Varaha — Andhra Pradesh Agroforestry — Klimate](https://www.klimate.co/project/varaha-andhra-pradesh-agroforestry)
- [Varaha — Banni Biochar — Klimate](https://www.klimate.co/project/varaha-banni-biochar)
- [Vann by Varaha — ARR dMRV — Google Play](https://play.google.com/store/apps/details?id=com.varaha.arrapp)

Methodologies and standards:
- [VM0047 Afforestation, Reforestation, and Revegetation v1.1 — Verra](https://verra.org/methodologies/vm0047-afforestation-reforestation-and-revegetation-v1-1/)
- [ICVCM approves VM0047 — Climate Impact Partners](https://www.climateimpact.com/news-insights/news/icvcm-approves-vm0047-arr-methodology/)
- [Sylvera named data service provider for VM0047](https://www.sylvera.com/blog/sylvera-verra-vm0047-dmrv-performance-benchmark-data-provider)
- [Major revision to VM0042 — Verra](https://verra.org/methodologies/revision-to-vm0042-methodology-for-improved-agricultural-land-management/)
- [Puro Standard biochar methodology](https://puro.earth/methodologies/biochar/)
- [Methane emission reduction by adjusted water management in rice cultivation — Gold Standard](https://globalgoals.goldstandard.org/standards/437_V1.0_LUF_AGR_Methane-emission-reduction-by-AWM-practice-in-rice-cultivation.pdf)

Market, policy and economics:
- [Carbon offset pricing trends 2026 — Sylvera](https://www.sylvera.com/blog/carbon-offset-price)
- [Carbon credit prices 2026 by project type — Regreener](https://www.regreener.earth/blog/carbon-credit-prices-today-trends-and-forecasts-for-2026)
- [Can carbon finance work for smallholder agriculture? — Climate Policy Initiative](https://www.climatepolicyinitiative.org/can-carbon-finance-work-for-smallholder-agriculture/)
- [Challenges for agriculture-based carbon credit projects in India](https://vishnuias.com/agriculture-based-carbon-credit-projects-in-india/)
- [India notifies emission intensity targets under CCTS — ICAP](https://icapcarbonaction.com/en/news/india-notifies-emission-intensity-targets-nine-sectors-under-carbon-credit-trading-scheme)
- [India CCTS guide 2026](https://rsustain.org/ccts-guide/)
- [Indian Carbon Market: CCTS and Article 6 — Offset8 Capital](https://offset8capital.com/articles/indian-carbon-market-ccts-article6/)

Remote sensing / dMRV technical:
- [A high-resolution canopy height model of the Earth](https://langnico.github.io/globalcanopyheight/)
- [Combining GEDI and Sentinel data to estimate canopy height and AGB — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1574954123003771)
- [Planet Forest Carbon Monitoring technical specification](https://docs.planet.com/data/planetary-variables/forest-carbon-monitoring/techspec/)
