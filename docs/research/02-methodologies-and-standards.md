<!--
  Implications first, fact base after. The fact base was assembled from
  search summaries of primary sources because the primary PDFs could not be
  fetched from the research environment; every fact is tagged accordingly,
  and src/carbonstack/standards.py carries the same tags into the product.
-->

# What the standards landscape means for us

Read with `01-mitti-labs-and-varaha.md`. That note answered *what the leaders
built*; this one answers *what the rules will let us issue, and where*. The
tagged fact base follows below; these are the conclusions that changed code.

1. **Rice issues without a buffer anywhere.** CH4 reductions are not
   buffered under Verra, Gold Standard or Isometric, because avoided methane
   cannot reverse. VM0051 v1.1 is CCP-approved and the only rice route on the
   CORSIA list. That is the strongest *label* position of any pathway we run.
2. **But an Indian rice tonne probably cannot reach CORSIA.** India's
   Article 6 activity lists appear to exclude agriculture and nature-based
   activities (unconfirmed, decision-relevant). Without a Letter of
   Authorisation and a corresponding adjustment, the CORSIA premium is not
   available to the Thanjavur pilot. `standards compare --corsia` blocks it
   rather than pricing it.
3. **Gold Standard 2026 vintages need Paris-aligned methodology versions** —
   A/R, rice and soil alike. A GS route for a 2026+ vintage on a legacy
   version is blocked, not discounted. This alone argues for Verra on the
   Kenyan coffee block.
4. **Buffers differ by more than any measurement improvement buys.** Verra's
   AFOLU minimum is 12% under the v5.0 NPRT procedure (10% under v4.0); Gold
   Standard's land-use buffer is a flat 20%. On the coffee block that gap is
   about 8 points of every tonne, forever.
5. **VCS v5 takes effect 1 January 2027.** Projects registering in 2026 do
   so under v4.7 and transition later; projects starting after 1 January 2027
   use v5.0B templates. A registration plan that straddles the date needs to
   say which.
6. **VM0042 is CCP-approved on the condition that SOC is not measured by
   digital soil mapping.** That is why the SoilGrids connector refuses to be
   a baseline: a modelled map can stratify and initialise RothC, never credit.
7. **Biochar is the only pathway where the durability class is a lab
   number.** Puro CORC200+ requires molar H/Corg < 0.7; Isometric's 200-year
   option requires < 0.5 and its 1,000-year option requires random
   reflectance. Varaha's biochar line runs through Puro; the H/Corg of our
   char decides which registries are open before any carbon is counted.
8. **India's own scheme now has rice and A/R methodologies** (BM AG04.002,
   BM FR05.001/002). A CCTS route is real but domestic: the same tonne must
   not also be issued internationally, and there is no traded price yet.
9. **Price follows label and rating, not only pathway.** CCP-labelled
   credits trade roughly 19–25% above the broad market; highly rated credits
   at several times low-rated ones. Both are secondary-sourced and are
   modelled as such.

What was **not** confirmed and must be checked against the standards' own
documents before any number here goes into a PDD: Verra's exact uncertainty
deduction (v4.3+ probability of exceedance), the Gold Standard land-use
uncertainty rule, Puro's 2025 decay equation, Isometric's buffer rates, and
which GWP set VCS v5 uses (CH4 28 vs 27 is a 3.6% swing on rice credits).

---

# Carbon-Credit Methodologies & Standards: Fact Base (Ag, Soil, ARR, Rice, Biochar, Blue Carbon)

**Status:** research note, 22 October 2026
**Scope:** methodologies and standards as they stand in 2025–2026. This note does not repeat the Mitti Labs / Varaha teardown (`docs/research/01-mitti-labs-and-varaha.md`).

## How to read this

**Access limitation (important).** In this session the egress proxy refused direct fetches of verra.org, icvcm.org, goldstandard.org, puro.earth, isometric.com, icao.int and the hubspot PDF host. WebFetch failed with DNS errors and curl received a 403 on CONNECT. Every fact below therefore comes from **web-search index summaries** of the pages cited. Full PDFs were not read. Tags:

- **[P]**: stated in a search snippet from a primary source domain (verra.org, icvcm.org, goldstandard.org, puro.earth, registry.isometric.com, icao.int, unfccc.int, beeindia.gov.in, msci.com, bezerocarbon.com).
- **[S]**: secondary source only (trade press, consultancies, aggregators).
- **UNCONFIRMED**: not found in any search result. Either from prior knowledge or the sources conflict. **Check before building on it.**

Before you hard-code any number (buffer %, uncertainty rule, decay formula), get the actual PDF and confirm it.

---

## 1. Verra – Verified Carbon Standard (VCS)

### 1.0 Program-level: VCS v4.7 → v5.0
- **VCS v5.0 package** (VCS Standard, Methodology Requirements, Registration & Issuance Process, *Procedure for Applying the AFOLU Non-Permanence Risk Tool v5.0*) was **issued 16 Dec 2025** [P].
  - Corrections and Clarifications followed on 24 Mar 2026 and 9 Jun 2026. The overview document was last updated 10 Sep 2026 [P].
  - **Most v5 requirements take effect 1 Jan 2027** [P].
  - VCS Standard v4.7 remains active until 1 Jan 2027 [P].
  - Template v5.0A applies to projects starting before 1 Jan 2027, and v5.0B to projects starting on or after that date [P].
  - Registered projects reportedly have until **1 Jan 2030** to transition [S].
- **Durability pilot (v5):** a 3-year pilot lets proponents manage reversal risk with insurance or a fund instead of the pooled buffer. Pilot VCUs carry an "innovation" label [P/S]. CORSIA-approved insurance cannot be used in the pilot, because it covers double-claiming risk, not reversal [P].
- **AFOLU crediting period (v4.7 §3.9.3):** the initial period is at least 20 and at most 100 years. It can be renewed up to 4 times, and the total cannot exceed 100 years [P, quoted in Verra's VM0042 FAQ].
  - ALM projects need **≥40-year project longevity** and a **baseline reassessment every 10 years** [P].
  - ALM projects that only reduce N2O/CH4/fossil CO2 follow the non-AFOLU rule: 7 years renewable twice (21 years total) or 10 years fixed [P, v4.0 summary].
  - Whether v5 changes these periods: UNCONFIRMED.
- **Uncertainty (VCS Methodology Requirements §2.4):**
  - v4.2 (effective 22 Dec 2022) introduced uniform, IPCC-based uncertainty estimation [P].
  - Consultation favoured the **90% confidence interval** as the basis, made projects with **>100% uncertainty ineligible**, and applied uncertainty discounting to ERR estimates but not to leakage [P, consultation summary; final wording UNCONFIRMED].
  - Since v4.3, the deduction uses the **"probability of exceedance"** method (cited in a VM0042 webinar) [P].
  - v5.0 Methodology Requirements still contain §2.4 "Uncertainty", but the text was not retrieved [P].
  - The common rule of thumb ("no deduction if the 90% CI half-width is ≤10% of the mean, otherwise deduct") comes from CDM and older VCS practice. Whether it applies under v4.3+/v5 is **UNCONFIRMED**.

### 1.1 AFOLU Non-Permanence Risk Tool (NPRT)
- **v4.2 (12 Oct 2023)** is the version in force under VCS v4.x [P]. v4.1 (29/30 Aug 2023) added climate-change and sea-level-rise risk, **increased minimum withholdings**, and added withholdings for past government intervention and for missing loss reports [P].
- Since 1 Jan 2024, projects must use the **digital NPRT calculator** [P].
- **Risk categories and failure thresholds (v4.2):** Internal, External and Natural risk. A project fails if Internal > 35, External > 20 or Natural > 35 [P]. The overall rating is rounded up to a whole percent and multiplied by the net change in carbon stock to give the buffer contribution [P].
- **Minimum buffer:**
  - **v4.0 (2019): 10%** [P].
  - **Procedure for Applying the AFOLU NPRT v5.0 (16 Dec 2025): 12%**, regardless of the calculated rating [P].
  - The exact v4.1/v4.2 floor was not visible in the snippets: **UNCONFIRMED**. The release notes say minimums were "increased", so it may already be 12% in v4.1/4.2.
- **Not buffered:** reductions of N2O, CH4 and fossil CO2, because they cannot be reversed [P]. This matters for rice: VM0051 CH4 reductions carry no buffer.
- Verra's buffer held about 60 Mt, roughly 15% of all AFOLU credits issued [S, 2022].
- Jurisdictional programmes use a separate JNR Non-Permanence Risk Tool (v4.1, 19 Aug 2024) [P].

### 1.2 VM0042 Improved Agricultural Land Management (IALM)
- **Version:**
  - **v2.2, active since 21 Oct 2025**. v2.1 remains available on a transition schedule [P].
  - Corrections and Clarifications to v2.2 were issued **11 Jun 2026** and are mandatory [P].
  - **v3.0 (major revision, consultation M0264)** ran from about 11/18 Feb to 20/31 Mar 2026 [P]. It proposes:
    - cumulative accounting of net reductions and removals;
    - a "blended baseline" across crop years;
    - standardised stratification, sampling and lab analysis;
    - a new **Soil Sampling & Analysis Handbook** (with equivalent soil mass).

    Verra says it will submit v3.0 to the ICVCM once it is final [P]. Finalisation was not found: UNCONFIRMED.
- **Scope:** reductions in GHG emissions and SOC removals from changed ALM practices, such as tillage, fertiliser, residue, cover crops, water and grazing [P].
- **Gases and pools:** SOC (CO2); N2O from fertiliser/manure; CH4 (e.g. from rice or enteric sources); fossil CO2 [P/S].
- **Baseline:** pre-project practices continued. v2.2 adds the rationale for this, aligns additionality with **VT0008**, and requires conservative, disaggregated emission factors [P].
- **Quantification approaches:**
  - **QA1 measure-and-model:** biogeochemical models calibrated and validated under **VMD0053**, e.g. DayCent or RothC. Verra notes DayCent needs a commercial licence for non-academic use and RothC is open source [P].
  - **QA2 measure-and-remeasure:** direct SOC sampling [P].
  - **QA3 default factors** (e.g. IPCC Tier 1 for N2O) [S].
  - **VT0014 Digital Soil Mapping** can support QA1 or QA2 [P].
- **Uncertainty:** the probability-of-exceedance deduction, aligned with VCS Methodology Requirements v4.3 [P]. Minimum sampling depth is **30 cm** (ICVCM Board observations) [P].
- **Buffer:** AFOLU NPRT applies to SOC. Not applicable to N2O/CH4 reductions [P].
- **Crediting / permanence:** 20–100-year AFOLU crediting, ≥40-year longevity, baseline reassessed every 10 years [P].
- **ICVCM:** **v2.2 CCP-approved with conditions in Oct 2025**, the first sustainable-agriculture approval alongside CAR SEP v1.1. **The condition: SOC must be measured with any allowed technique *except Digital Soil Mapping (DSM)*.** DSM was not assessed [P]. The CAR SEP approval requires a project agreement with a ≥40-year permanence commitment and excludes rotational/intensive grazing [P].
- **CORSIA:** UNCONFIRMED for VM0042 specifically. VCS is approved at programme level for Phase 1, but methodology exclusions may apply.

### 1.3 VMD0053 Model Calibration, Validation & Uncertainty Guidance
- **v2.1, active since 25 Mar 2025** [P].
  - It generalises guidance on process-based biogeochemical models to all ALM methodologies, not just VM0042 [P].
  - Projects validated under v2.0 may keep using v2.0 until their next baseline reassessment or crediting-period renewal [P].
  - It is in scope of the 2026 VM0042 v3.0 consultation [P].
- Specific acceptance thresholds (e.g. bias or RMSE limits, number of sites per crop functional group): **UNCONFIRMED**. Read the PDF.

### 1.4 VM0047 Afforestation, Reforestation & Revegetation (ARR)
- **Version:** **v1.1, active since 14 May 2025**, a minor revision [P]. v1.0 projects had to be pipeline-listed by 31 Dec 2025 and must request registration by **31 Dec 2026** [P].
- **Two approaches:**
  - **Area-based:** a **dynamic performance benchmark** derived from remote sensing. At each verification, the change in a remotely sensed **stocking index** in project plots is compared with **matched control plots** outside the project. The benchmark sets both additionality and the crediting baseline. Leakage is handled with **VMD0054** (displacement of pre-project agriculture) [P].
  - **Census-based:** for ARR outside forests with no land-use change, e.g. trees on farms or agroforestry. It is exempt from leakage [P].
- **Pools:** above- and below-ground tree biomass. Optional pools (dead wood, litter, SOC, non-tree biomass) are included in the methodology: **UNCONFIRMED** detail.
- **Uncertainty:** Appendix 3 (revised in v1.1). Detail **UNCONFIRMED**.
- **Buffer:** AFOLU NPRT, with a minimum of 12% under v5 [P].
- **Crediting:** AFOLU 20–100 years [P].
- **ICVCM:** v1.0 approved **12 Dec 2024**, and **v1.1 approved 1 Oct 2025**. Credits under either version are CCP-eligible. It was the first nature-based methodology approved that uses remote sensing for a dynamic benchmark [P].

### 1.5 VM0048 Reducing Emissions from Deforestation and Forest Degradation (REDD) + VMD0055
- **VM0048 v1.0** with module **VMD0055 v1.1** (avoided unplanned deforestation, AUD) [P].
  - Baselines come from **jurisdictional deforestation-risk maps produced by Verra's data providers**. Expected deforestation is **allocated** to projects, which caps the sum of project baselines in a jurisdiction [P/S].
  - Provisional 1-ha risk maps were released Jan 2025 [P].
  - Activity data is discounted for statistical uncertainty before allocation [P]. Calyx reports that activity-data uncertainty must be ≤20%, with a downward adjustment if it exceeds 10% [S].
- **Transition:** legacy AUD projects using VM0006/7/9/15/37 must move to VM0048 at their next baseline reassessment or after a grace period once activity data is released. Their credits will be re-quantified [P].
- **ICVCM:** **approved Nov 2024 (VM0048 v1.0 + VMD0055 v1.1)**, together with **JNR Framework v4.1** and **ART TREES v2.0** (TREES crediting level) [P].
  - A later clarification included projects nested in JNR Scenario 1 [P].
  - **Legacy REDD methodologies (VM0006, VM0007, VM0009, VM0015, VM0037) were withdrawn from assessment and cannot carry CCP labels** [P].
  - ART TREES **v2.0 HFLD crediting level was found not to meet the CCPs** [P]. In May 2026, ART HFLD and Removals were sent back for remedial action [S].

### 1.6 VM0051 Improved Management in Rice Production Systems
- **Versions:** v1.0 active from 27 Feb 2025, to be inactivated **1 Aug 2027**. **v1.1 active since 14 Jul 2026** [P]. It replaces the inactivated CDM methodology **AMS-III.AU** [P].
- **Scope:** improved water and crop management in **flooded rice**, e.g. AWD, single or multiple drainage, DSR, and other changes [P].
- **Baseline:** pre-project practices continued, based on a historical look-back covering irrigation and water regime, planting dates, fertiliser, drainage events, harvest and off-season practice [P]. v1.1 requires **baseline reassessment every 5 years** or at crediting-period renewal [P].
- **Additionality:** regulatory surplus, barrier and/or investment analysis, and a common-practice test [P].
- **Quantification approaches:**
  - **QA1** process-based biogeochemical model (e.g. DNDC-type);
  - **QA2** direct CH4 measurement (chambers);
  - **QA3** default equations and emission factors (IPCC). There is a simplified QA3 route for projects of **≤60,000 tCO2e/yr** [P].

  The approaches allowed differ by GHG source and project scale [P].
- **Gases:** CH4 is primary, plus N2O and SOC changes [S].
- **Buffer:** CH4 reductions are not subject to buffer withholding [P].
- **Uncertainty and crediting period:** details UNCONFIRMED. This is likely an ALM GHG-only project, so the 7-year ×3 / 10-year rule would apply: UNCONFIRMED.
- **ICVCM:** **v1.1 CCP-approved (Verra announcement 12 Aug 2026)**. Credits get the label if they meet all eligibility conditions [P].
- **CORSIA:** ICAO TAB included **VM0051 v1.0 credits "for projects in REDD+ countries"** for **Phase 1 (2024–26) and Phase 2 (2027–29)**, subject to host-country authorisation (Verra, 16 Apr 2026) [P]. The meaning of the "REDD+ countries" restriction was not confirmed against the TAB text.

### 1.7 VM0033 Tidal Wetland & Seagrass Restoration
- **v2.1, active since 4 Sep 2023.** This was a minor revision [P]:
  - the latest NPRT must be used for **sea-level-rise** (erosion and submergence) risk;
  - the project area may move landward over the crediting period.
- **Pending v3.0** (major revision with a modular structure): consultation ran **3 Sep – 5 Oct 2026** [P]. A proposal to add "human-controlled wetlands" was rejected on 1 Apr 2026 because those activities are already eligible [P].
- **Pools and gases:** above- and below-ground biomass, SOC (sometimes wood products), CH4 and N2O [P/S]. **Allochthonous carbon** (SOC deposited from outside the project) is defined in **VMD0051**, and the stable allochthonous fraction is deducted. The formula is UNCONFIRMED [P].
- **Buffer:** AFOLU NPRT, including sea-level-rise risk [P].
- **ICVCM:** no VM0033 decision was found. **UNCONFIRMED / likely not yet assessed.** The first CCP-approved blue-carbon methodology is **Isometric's Mangrove Restoration Protocol v1.0** (board decision 30 Apr 2026, announced 11 May 2026) [P].

### 1.8 VM0044 Biochar Utilization in Soil and Non-Soil Applications
- **v1.2, active since 27 Jun 2025.** This minor revision added an **investment analysis** for additionality so that the methodology aligns with the CCPs [P]. v1.1 projects had to be listed by 27 Jun 2025 and validated by 27 Dec 2025 [P].
- **Scope:** CDR from converting **waste biomass** into biochar at **new** facilities. The biochar can be applied to crop or grassland soils or used in non-soil products such as concrete and building materials [P].
- **Permanence:** Section 8.4 covers the decay rate and reversal risk [P]. The decay model (likely Woolf-type, based on H/Corg and soil temperature, with a 100-year horizon) and any buffer %: **UNCONFIRMED**.
- **ICVCM:** **v1.2 approved Aug 2025** (with VM0045 IFM v1.2), in the same batch as CAR US & Canada Biochar v1.0 and Isometric Biochar Production & Storage v1.0 [P/S].
- **2026:** a v2.0 draft is under independent expert review (Verra RFP, 4 Aug 2026) [P].

### 1.9 Verra's CCP-label mechanics
- The ICVCM approved VCS as a **CCP-Eligible programme on 25 Apr 2024** [P].
- Verra **auto-applies CCP labels** at issuance when the project uses only CCP-approved methodologies and the information is sufficient [P]. More than 10M VCUs were labelled by 6 Jun 2024 [P].
- Proponents can **request** labels manually. A digital form was planned for 2025 [P].
- Labels cannot be applied **retroactively to retired VCUs**, or to VCUs issued under earlier, non-approved versions of a methodology [P].
- Methodology-specific conditions (e.g. the DSM exclusion for VM0042, VMD0055 for VM0048) are checked by the VVB and Verra at verification [P].
- The CCP label is separate from the **"Article 6 Authorized – International Mitigation Purposes"** label. That label is required, for vintages 2021 onward, to receive the "CORSIA First Phase 2024–2026 Eligible" label [P].

---

## 2. Gold Standard for the Global Goals (GS4GG)

### 2.1 Afforestation/Reforestation
- **A/R GHG Emissions Reduction & Sequestration Methodology:** **v2.1 (16 May 2024) is current**. v2.0 dated from 26 Oct 2022 [P]. It is used with the GS4GG LUF Activity Requirements.
- **ICVCM:** no decision found on the GS A/R methodology [S/UNCONFIRMED].
- **Paris-alignment programme:** **non-PA-aligned methodologies are being retired, and PA-aligned versions are mandatory for all vintage-2026 issuances.**
  - Land-use methodologies (A/R, rice, soil carbon) are scheduled under this framework from 2026 [P/S].
  - Developers objected that this applies retroactively to registered projects [S].
  - **This is decision-critical for any GS project issuing 2026-vintage credits.**

### 2.2 Soil Organic Carbon Framework Methodology
- **v1.0, released 28 Feb 2020** (dated Jan 2020; developed by TREES Consulting). No later version was found [P].
- **Approaches:** three quantification approaches — direct measurement, models, and approved default factors [P].
- **Activity modules:** Improved Tillage (zero/no-till), which replaced the GS v0.9 tillage methodology; Biostimulant application. There is a module-development procedure (402.1) [P].
- Gold Standard consulted on **SOC Model Requirements & Guidelines** in Jan 2025 [P].
- The ESRP (European Soil Revitalisation Programme) was the first issuance under the framework [P].
- **ICVCM:** no decision found. UNCONFIRMED.

### 2.3 Rice: "Methane Emission Reduction by Adjusted Water Management Practice in Rice Cultivation"
- **v1.0, published 6 Jul 2023.** It was consulted on Oct–Nov 2022 and replaces CDM AMS-III.AU within GS4GG. The next planned update was 5 Jul 2026 [P/S]. Whether a v2.0 or PA-aligned version has been published: **UNCONFIRMED**.
- **Practices:** a change from continuous to intermittent flooding or a shorter flooded period; AWD; aerobic rice; transplanting → DSR [P].
- **Approach:** aligned with **IPCC 2019, Ch. 5.5**. It allows country-specific Tier-2 baselines and methane measurements. Simplified approaches exist for small- and micro-scale projects, and PoAs are allowed [P]. The 60,000 t threshold was not confirmed for the GS methodology.
- **ICVCM:** **CCP-approved *with conditions* (board decision 29 Jan 2026; published Feb 2026)** [P]:
  1. **Additionality must use Option 3, project-specific activity penetration.** The Board found that only this option sets a quantitative AWD-share threshold.
  2. Projects must apply the updated rule on **soil organic carbon loss risk**.

  About **50,000 credits** had been issued, and none complied with condition 1, so **none of the existing issuances are CCP-eligible**. GS plans up to **3.2M credits over 5 years** [S, citing ICVCM].

### 2.4 Buffer, uncertainty, SDG impacts, registry
- **Compliance Buffer (LUF):** **20% of GS VERs** at each issuance go to the Gold Standard-administered Compliance Buffer. The alternative is eligible substitute credits, requested in writing before issuance [P, GS terms & conditions].
  - Reversals are compensated by retiring buffer credits [P].
  - Whether the GS SOC framework uses the same 20%: **UNCONFIRMED**.
  - The UNCONFIRMED recollection that the risk-based buffer can be reduced (e.g. to 10–20%) was not verified.
- **Uncertainty:**
  - Gold Standard consulted (9 Sep – 8 Oct 2024) on "Requirements for Uncertainty Assessment and Addressal in GS4GG Methodologies". It **explicitly excludes LUF activities** [P]. Whether it was finalised: UNCONFIRMED.
  - There is an older Uncertainty Assessment Tool (9 Dec 2020) [P].
  - The LUF sampling precision target (90/10) is **UNCONFIRMED** for GS.
- **SDG impact:** the **SDG Impact Tool** has been **mandatory for projects submitted to Preliminary Review after 14 Mar 2022**. The digital tool fully launched after a Q4 2023 soft launch [P]. The certified tool output must be published on the **Gold Standard Impact Registry** [P]. There is also a public SDG Impact Dashboard and an SDG Impact Tool guide for rice projects [P].
- **Impact Registry:** tracks certification status, issuances and certified SDG impacts. Projects must reach "Listed" status to apply the SDG tool [P].

---

## 3. Puro.earth

- **Programme status:** **ICVCM CCP-Eligible programme (11 Dec 2025)**, the 8th programme, on Puro Standard **v4.2** [P].
  - Its biochar, carbonated-materials and geological-storage methodologies have **not yet** been assessed by the ICVCM, so there are no CCP labels yet [P].
  - CORSIA: Puro's 2024 application found v4.0 only "partially consistent". Puro is not on the Phase 1 list [S].
- **CORC:** the CO2 Removal Certificate. One CORC = **1 tCO2 net removed and durably stored, ≥100 years** under the Puro Standard (CORC100+). Biochar is now CORC200+ [S for the definition; P for CORC200+].

### 3.1 Biochar Methodology
- **Edition 2025, approved 12 Jun 2025.** "Version 2" has been published, plus a later minor rule change that allows "Retail to individuals" end use [P].
  - The headline change is a move from **CORC100+ to CORC200+**, a claim of "several centuries", using a **revised decay (decomposition) equation** [P].
- **Edition 2022 (V3):** the permanence factor came from **Woolf et al. 2021**. It is a function of **H/Corg (or pyrolysis temperature)**, **time horizon (100 years)** and **soil temperature**. Expected 100-year re-emissions were deducted [P, EU workshop deck and Puro].
- **Eligibility: molar H/Corg < 0.7** [S/P snippets].
- **Lab parameters:** organic carbon content, H/Corg, PAH and heavy metals [P]. A full lab-parameter list and EBC-equivalent limits are **UNCONFIRMED**.
- **Random reflectance (Ro, inertinite):** **encouraged / voluntary in Edition 2025, but it does not affect quantification** [P, Puro]. Some commentary describes a "Ro 2% inertinite benchmark" [S].
  - An **Azzi et al. 2024 inertinite option in Puro: UNCONFIRMED.** The inertinite-based 1,000-year option is an **Isometric** feature that cites Sanei et al. 2024.
- **Revised decay formula for Edition 2025: UNCONFIRMED.** Take it from the PDF.
- **LCA deductions:** the CORC count is net of life-cycle emissions (biomass sourcing, transport, production, use) and the decay loss. Exact rules are **UNCONFIRMED**.

### 3.2 Enhanced Rock Weathering Methodology
- **Edition 2025, announced 17 Nov 2025** and aligned with the Puro General Rules and the CCPs [P].
  - 144 public comments led to 91 minor and 4 major changes.
  - There are **7 eligible quantification approaches**. A project must combine **one approach that quantifies stored CO2 with one that validates it**.
  - **Site-specific field measurement is always required. Modelling is optional** [P].

---

## 4. Isometric

- **Registry model:** Isometric is both standard-setter and registry. Protocols and modules are versioned on registry.isometric.com [P].
  - **Isometric Standard v2.0 (Apr 2026)** refined the **buffer-pool** framework for open-system pathways, extended default crediting periods, and formalised how protocol versions apply over time [P].
  - Buffer credits are held per supplier and cancelled when a reversal occurs [P].
  - Isometric argues that OAE, EW and biochar have no plausible re-release mechanism [P].
- **CORSIA:** Isometric is on the Phase 1 programme list (TAB approval, early 2026) [S]. Scope limits are UNCONFIRMED.
- **ICVCM:** CCP-approved protocols, as reported [P/S]:
  - Biochar Production & Storage v1.0 (Jul/Aug 2025);
  - five engineered CDR protocols (autumn 2025): Biomass Geological Storage, Bio-oil Geological Storage, Subsurface Biomass Carbon Removal & Storage, BECCS, DAC;
  - **Reforestation v1.1** (Feb 2026, with no conditions);
  - **Mangrove Restoration v1.0** (Apr/May 2026; its 8th approved protocol).
- **Biochar protocol** (certified Oct 2024; protocol now at v1.3; soil storage module v1.2/1.3):
  - **200-year durability option** uses an **H/Corg-based decay curve**. Only biochar with **H/Corg < 0.5** qualifies, which is stricter than Puro's 0.7 [P].
  - **1,000-year option** requires **random reflectance (Ro)** to quantify the **inertinite fraction**. It cites Sanei et al. 2024, with an **Ro threshold of 2%** for the creditable inertinite fraction [P].
  - The built-environment module (v1.0, e.g. concrete) applies a safety factor of 3 for exposure over 1,000 years. It must not use the Woolf 200-year model [P].
  - A CRCF-aligned biochar requirements module exists (v1.0) [P].
- **Enhanced Weathering in Agriculture protocol:** certified Apr 2024; v1.1 and **v1.2** exist [P]. The durability horizon and ICVCM status are **UNCONFIRMED** (no ICVCM EW decision was found).
- **Agriculture protocols (2026):**
  - **Rice methane protocol** (AWD and related practices): draft Apr 2026 with consultation to 7 May. Reported **certified late May 2026** with a first supplier named [S; headline only].
  - **Improved Soil Management (soil carbon) protocol:** **certified 15 Jul 2026** with a Cropland Management module. A grazing-lands module is in development, and 3 developers registered at launch [S].

---

## 5. ICVCM Core Carbon Principles: status by category (as of Oct 2026)

**Programmes CCP-Eligible:**
- Verra VCS (25 Apr 2024), Gold Standard, ACR, CAR, ART, Isometric and GCC (reported) [P/S].
- **Puro.earth** (Dec 2025, 8th) [P].
- **BioCarbon Standard, Cercarbono, Plan Vivo (PV Climate)** (Aug 2026). CCP-Eligible programmes now cover more than 95% of cumulative VCM issuance [S].

Totals [S]: about 40 methodologies approved and 25 rejected as of May 2026, and about 115M credits approved for the CCP label by Aug 2026.

| Category | Status | Key items |
|---|---|---|
| **ARR** | Approved | VM0047 v1.0 (Dec 2024) & v1.1 (Oct 2025); Isometric Reforestation v1.1 (Feb 2026). GS A/R: no decision found |
| **IFM** | Approved (some conditional) | VM0045 v1.2 (Aug 2025); ACR IFM non-federal US v2.1 (8 Aug 2025, conditional on leakage deduction below 5% de minimis); ACR IFM v2.0 conditional (Feb 2026) |
| **REDD+** | Approved (new only) | VM0048 + VMD0055 v1.1, JNR v4.1, ART TREES v2.0 (Nov 2024). **Legacy VM0006/7/9/15/37 excluded.** ART HFLD crediting level rejected |
| **Sustainable agriculture / soil (ALM)** | Approved with conditions (Oct 2025) | VM0042 v2.2 (**no DSM**), CAR SEP v1.1 (≥40-year PIA; no rotational/intensive grazing) |
| **Rice methane** | Approved | GS rice v1.0 conditional (Jan/Feb 2026: activity penetration only + SOC-loss rule); **VM0051 v1.1** (Aug 2026) |
| **Biochar** | Approved | VM0044 v1.2, Isometric Biochar v1.0, CAR US&Canada Biochar v1.0 (Jul–Aug 2025). Puro biochar not yet assessed |
| **Blue carbon** | Approved (Isometric only) | Isometric Mangrove Restoration v1.0 (Apr/May 2026). VM0033: no decision found |
| **Engineered CDR** | Approved | 5 Isometric protocols + GS accelerated carbonation of concrete aggregate (conditional), autumn 2025 |
| **ERW** | Not found | No ICVCM ERW decision found (UNCONFIRMED) |
| **Renewable energy** | **Rejected** (Jul 2024) | 8 CDM-derived grid RE / biomass methodologies, rejected on additionality and grid-factor tool grounds. VMR0017 v1.0 (Verra, renewable electricity) approved with conditions May 2026 [S] |
| **Other** | Mixed | Landfill gas approved (Verra, with rice); ACM0008 coal mine methane conditional (VAM/CMM only, May 2026) |

---

## 6. CORSIA

- **Phase 1 = 2024–2026 compliance period.** Eligible units come from activities whose **first crediting period started on or after 1 Jan 2016**, for reductions/removals that occurred **1 Jan 2021 – 31 Dec 2026** [S, consistent with ICAO doc].
- **Host-country Letter of Authorisation (LoA) + corresponding adjustment (CA) are required.** Unlike the Pilot Phase, Phase 1 units are eligible only where the host country applies a CA [S/P].
  - Programmes also need either a programme-level guarantee or insurance against non-CA ("double-claiming" insurance) [S].
  - Verra implements this with the **Article 6 Authorized** label plus a **CORSIA First Phase Eligible** label [P].
- **Approved programmes, Phase 1** (ICAO "CORSIA Eligible Emissions Units", Apr 2026 edition; via secondary summary):
  - ACR, ART, BioCarbon Fund ISFL, CAR, FCPF, GCC, Gold Standard, **Isometric**, Premium T-VER, Verra VCS (10 programmes).
  - Earlier lists show 8, without ISFL and FCPF [S].
  - Each approval carries methodology and activity exclusions [S].
- **Phase 2 (2027–2029):** ACR, ART, Gold Standard and VCS approved after TAB re-assessment (ICAO Council, Oct 2025) [P/S]. TAB is applying stricter LoA requirements for Phase 2 [S].
- **Supply (conflicting) [S]:**
  - About 36–41M eligible units issued and labelled.
  - Sylvera: 38M of roughly 300M potentially eligible units had cleared both authorisation and CA.
  - IATA: about 72M units covered by 42 LoAs (Aug 2026), but only 5 countries had reported CAs by Jun 2026.
- **Deadline:** cancellation of Phase 1 units is due by **31 Jan 2028** [S].
- **Ag relevance:** **VM0051 rice is CORSIA-eligible (Phase 1 & 2)**, subject to the "REDD+ countries" qualifier and an LoA [P].

---

## 7. Article 6.4 – Paris Agreement Crediting Mechanism (PACM)

- **Standards (in force 9 Oct 2024):** the **Methodology Standard** ("Application of the requirements of Chapter V.B") and the **Removals Standard** ("Requirements for activities involving removals", A6.4-STAN-METH-002), adopted at SBM014 in Baku [P/S].
  - The Removals Standard creates a **Reversal Risk Buffer Pool Account**. Paragraph 62 sets a review of buffer robustness (stress tests, insurance, Party replenishment) [P].
- **Standard "Addressing non-permanence and reversals" v01.0:** considered at SBM018 (6–10 Oct 2025) and published 17 Oct 2025 (A6.4-SBM018-A13) [P].
  - **Updated leakage and non-permanence standards (v02.0) enter into force 9 Oct 2026** [P].
  - A **Reversal Risk Assessment methodological tool** was on the SBM023 agenda (5–9 Oct 2026). Its outcome is UNCONFIRMED [P].
- **First methodology:** **A6.4-AMM-001 "Flaring or use of landfill gas"** (derived from ACM0001), approved at SBM019 on 29–30 Oct 2025 [P/S].
  - It is the **only PACM-originated methodology** on the UNFCCC methodologies page. A clarification was approved at SBM021 on 21 May 2026 [P].
  - **No PACM agriculture, ARR, rice or biochar methodology had been approved** as of the material found [P/S].
  - The 2026 workplan includes a common-practice tool and a sampling & surveys standard [P].
- **CDM transition:**
  - **CDM A/R activities may transition** (CMA.6 decision). The deadline to *request* transition was **31 Dec 2025** [P].
  - The host-Party approval deadline for CDM transitions was extended from 31 Dec 2025 to **30 Jun 2026** [P]. Whether this extension covers A/R is ambiguous in the sources.
  - Transitioned activities may use their CDM methodology until the end of their current crediting period or 31 Dec 2025, whichever is earlier [P].
- **First issuance:** the **first A6.4ERs** were issued Q1 2026 from transitioned CDM activities [P]. Reported details: approved 26 Feb 2026, about 603k tCO2e, about 40% below the CDM equivalent [S].
- **GWP:** Paris transparency reporting uses **AR5 GWP100 (Table 8.A.1, excluding the fossil-methane value)** under 18/CMA.1 and 5/CMA.3 [P]. Whether PACM methodologies mandate AR5 is UNCONFIRMED, but likely.

---

## 8. India – Carbon Credit Trading Scheme (CCTS) offset mechanism & Article 6

- **Legal basis and institutions:**
  - CCTS was notified in 2023 under the Energy Conservation Act. The **Bureau of Energy Efficiency (BEE) is the administrator** [P/S].
  - **Grid Controller of India Ltd (Grid-India) is the registry** for the Indian Carbon Market [P, Dept of Land Resources doc].
  - The **"Detailed Procedure for the Offset Mechanism"** (Ministry of Power, ~Mar 2025) covers PDD → validation → registration → verification, with a **30-day public stakeholder comment period** on draft PDDs [S].
  - The Indian Carbon Market Portal launched **21 Mar 2026**. The first CCC trading was expected around mid-2026 [S, ICAP].
- **Sectors:**
  - **Phase 1:** energy, industry, waste, agriculture, forestry, transport. Biochar appears under agriculture and waste [P, BEE OM, Sep/Oct 2024].
  - **Phase 2:** construction, fugitive emissions, solvents, CCUS [S].
- **Methodologies:** BEE consulted on 12 drafts (comments due 30 Jan 2025). Reports cite **8 then 9 approved** [S]. Items on BEE's page include [P]:
  - **BM AG04.002**: Emission reduction through **improved management practices in rice cultivation** (AWD, aerobic, transplanted → DSR; can also cover N management, avoided residue burning, low-emission varieties and biochar). It was reportedly published around 30 Jun (2025) [S].
  - **BM FR05.001**: A/R of **degraded mangrove** habitats.
  - **BM FR05.002**: A/R of lands **except wetlands**. This is the likely route for agroforestry/ARR.
  - Others include industrial energy efficiency, landfill methane, green hydrogen, pumped hydro and biochar [S].
  - "Two agriculture methodologies approved" [S].
  - **A standalone agroforestry methodology is UNCONFIRMED**, and so is a standalone soil-carbon methodology.
- **Article 6:**
  - The NDAIAPA list (OM of 20 Feb 2023) covers 13 activities, for 3 years initially [S/P]:
    - renewable energy with storage, solar thermal, offshore wind, green hydrogen, compressed biogas, fuel-cell mobility, high-end energy efficiency, SAF, best available technology (BAT) for hard-to-abate sectors, tidal/ocean energy, HVDC linked to renewables;
    - green ammonia;
    - **CCUS as the only removal.**
  - **Jun/Jul 2024:** the 6.2 list was updated and a **separate 6.4 list** was finalised [S]. Contents are UNCONFIRMED.
  - **Nature-based / agriculture activities do not appear on India's Article 6 export lists as far as found.** So Indian ag/ARR credits probably will not get an LoA/CA, which matters for CORSIA and for the VM0051 CORSIA route. Treat this as UNCONFIRMED but decision-relevant.

---

## 9. Market prices 2025–2026 (indicative; mostly secondary)

| Type | 2025–26 price indications | Source quality |
|---|---|---|
| **ARR (nature-based removal)** | High-quality ARR spot **$14 → $24/t** (Jan → Sep 2025, Sylvera). Avg ~$22. BBB+-rated ~$28.55 vs low-rated ~$9.12 (H1 2026) | [S, Sylvera/aggregators] |
| **REDD+** | Avg ~$6. High-rated $8.40 (+71% y/y, H1 2026) vs low-rated $1.82 | [S] |
| **Rice methane (AWD)** | **$15–25/t** most cited. One source $18–35 | [S, weak]; no registry/primary data |
| **Soil carbon (ALM)** | Wide spread: $10–30, $20–60, ~$80 | [S, weak] |
| **Biochar CDR** | **~$100–250/t**. Avg ~$177 (Sylvera). Forward $155 vs spot $185 for the same project (2025, Supercritical). CDR.fyi/OPIS: +10% expected in 2026, bid-ask gap $107 → $98 | [S] |
| **CCP-label premium** | ICVCM: **~25% average premium** (ClearBlue/Calyx data). **MSCI Global CCP Carbon Credit Price Index ~19% above the broad VCM** since mid-2024. Abatable: ~14% uplift. 2024 brokers: ~$1/t | [S citing ICVCM/MSCI] |
| **Ratings premium** | Higher-rated credits trade at 4–5× lower-rated (Sylvera Q2 2026). BeZero: ~40% average premium per notch | [S] |

CCP-labelled supply: 16.6M credits issued with CCP labels in 2025 YTD by Q3 [S, Sylvera].

---

## 10. Ratings agencies – scales

| Agency | Scale | Notes |
|---|---|---|
| **Sylvera** | **AAA → D** | Three pillars: carbon score (incl. additionality and over-crediting), permanence, plus co-benefits and risk overlays [P/S] |
| **BeZero** | **8-point AAA → D** (moved from 7-point AAA–D) | Likelihood that a credit achieves 1 t CO2e. Outstanding ratings were mapped without re-analysis [P] |
| **Calyx Global** | GHG rating **AAA → D since Jan 2025** (previously A+ → E). SDG rating +1 → +5 | [S]. Primary confirmation UNCONFIRMED |
| **MSCI (ex-Trove)** | **7-point AAA → CCC** | 6 criteria and 50+ sub-criteria (additionality, quantification, permanence, co-benefits, legal/ethical, delivery). More than 4,000 projects, incl. pre-registration. Launched Sep 2024 [P] |

---

## 11. Default reference values

| Parameter | Value | Status |
|---|---|---|
| IPCC 2019 Refinement baseline EF, continuously flooded, no organic amendment (Table 5.11) | **Global 1.19 kg CH4/ha/day**; **South Asia 0.85** (range 0.58–1.26) | [P-ish, NIES/IPCC presentation] |
| Water-regime scaling factor SFw (2019, Table 5.12) | Continuously flooded **1.00**; **single drainage 0.71**; **multiple drainage 0.55**; rainfed regular 0.54; drought-prone 0.16; deep water 0.06; upland 0 | **1.00, 0 and 0.55 confirmed [S citing IPCC]. 0.71 and the rest UNCONFIRMED** (from memory). The 2006 GL values were 0.60 (single) and 0.52 (multiple), so do not mix the two versions |
| Pre-season scaling factor, non-flooded <180 days (Table 5.13) | 1.00 | [S citing IPCC] |
| GWP100 **AR5** (Table 8.A.1) | **CH4 28**; **N2O 265** | Standard values; **not re-verified in this session** (UNCONFIRMED here). AR5 is the UNFCCC/Paris reporting basis [P] |
| GWP100 **AR6** (WGI Table 7.15) | **CH4 non-fossil 27.0; CH4 fossil 29.8**; N2O **273**; (CH4 "solely methane" 27.9) | [S citing AR6] |
| Carbon fraction of dry wood (IPCC 2006 Table 4.3 default) | **0.47** | **UNCONFIRMED** in search (standard value) |
| Root:shoot ratios | Updated in **2019 Refinement Table 4.4** by ecozone, forest type, natural vs planted, and AGB class. The 2006 tropical rainforest value is 0.37 | 0.37 **UNCONFIRMED**. Table 4.4 update confirmed [S] |

**Which GWP set to use:** each methodology names its own. Verra currently follows IPCC AR5 under VCS v4. Whether VCS v5 moved to AR6 is **UNCONFIRMED**. Check this before coding, because CH4 28 vs 27 is a ~3.6% swing in rice credits.

---

## 12. Cross-standard comparison: buffer / uncertainty / permanence

| Standard / method | Non-permanence mechanism | Typical buffer | Uncertainty rule | Permanence / longevity horizon | CCP | CORSIA |
|---|---|---|---|---|---|---|
| **Verra AFOLU (VM0042 SOC, VM0047, VM0033, VM0048)** | AFOLU NPRT v4.2 → v5.0 procedure (pooled buffer); v5 durability pilot (insurance/fund) | Risk-scored. **Min 10% (v4.0) → 12% (v5.0)**. Typical 10–20% (UNCONFIRMED typical) | §2.4: IPCC-based, 90% CI, probability-of-exceedance deduction; >100% uncertainty ineligible | AFOLU crediting 20–100 years; ALM longevity ≥40 years; baseline reassessment every 10 years (ALM) | VM0042 v2.2 (no DSM), VM0047, VM0048: yes. VM0033: no decision | VCS programme Phase 1 & 2. Method exclusions apply |
| **Verra VM0051 rice** | Not buffered (CH4/N2O irreversible) | 0% | QA-dependent. Detail UNCONFIRMED | Baseline reassessed every 5 years (v1.1) | v1.1 yes (Aug 2026) | **Yes, Phase 1 & 2 (REDD+ countries qualifier, LoA)** |
| **Verra VM0044 biochar** | Decay model + reversal risk (§8.4) | UNCONFIRMED | VCS §2.4 | ~100-year decay basis (UNCONFIRMED) | v1.2 yes | Programme-level only |
| **Gold Standard LUF (A/R, SOC)** | Compliance Buffer | **20%** (or substitute credits) | 2024 uncertainty requirements exclude LUF. LUF rules UNCONFIRMED | PA-aligned versions required for 2026 vintages | A/R and SOC: no decision found | GS Phase 1 & 2 |
| **Gold Standard rice** | n/a (CH4) | 0% | IPCC 2019, Tier 2 options | — | Conditional (activity penetration + SOC-loss rule) | GS programme |
| **Puro biochar** | Decay deduction (Woolf 2021 → revised 2025 equation); Puro buffer UNCONFIRMED | UNCONFIRMED | Conservative LCA | **CORC200+** (2025). Other CORCs ≥100 years | Programme eligible; methods not assessed | Not approved |
| **Puro ERW** | Measurement-based (2 approaches: quantify + validate) | UNCONFIRMED | Field measurement mandatory | ≥100 years (CORC) | Not assessed | No |
| **Isometric biochar** | Buffer pool (Standard v2.0) | UNCONFIRMED | Protocol-specific | **200 years (H/Corg <0.5) or 1,000 years (Ro/inertinite)** | Yes (v1.0) | Isometric is a Phase 1 programme |
| **Isometric reforestation / mangrove** | Buffer pool | UNCONFIRMED | Protocol-specific | UNCONFIRMED | Yes | Isometric programme |
| **PACM (Art 6.4)** | Reversal Risk Buffer Pool; post-crediting monitoring; non-permanence standard v02.0 (Oct 2026) | Via Reversal Risk tool (pending) | Sampling standard in 2026 workplan | Removals Standard | n/a | n/a (A6.4ERs can be authorised) |
| **CAR Soil Enrichment** | PIA + buffer | UNCONFIRMED | — | **≥40-year PIA** | Yes (condition) | CAR programme |

---

## Sources

1. Verra – VM0042 IALM v2.2 page: https://verra.org/methodologies/vm0042-improved-agricultural-land-management/
2. Verra – ICVCM approves VM0042 (Oct 2025): https://verra.org/verras-improved-agricultural-land-management-methodology-approved-by-icvcm/
3. ICVCM – First sustainable agriculture methodologies approved (CAR SEP, VM0042): https://icvcm.org/integrity-council-approves-first-sustainable-agriculture-methodologies-from-car-and-verra/
4. ICVCM – Board Observations, Sustainable Agriculture: https://icvcm.org/wp-content/uploads/2025/10/Board-Observations_Sustainable_Agriculture.pdf
5. Verra – VM0042 major revision consultation (v3.0): https://verra.org/verra-consults-on-major-revision-to-improved-agricultural-land-management-methodology-vm0042/
6. Verra – VM0042 FAQ (AFOLU crediting period, ALM longevity): https://verra.org/methodologies-main/frequently-asked-questions-vm0042/
7. Verra – VMD0053 v2.1: https://verra.org/methodologies/vmd0053-model-calibration-validation-and-uncertainty-guidance-for-the-methodology-for-improved-agricultural-land-management-v2-1/
8. Verra – VT0014 DSM (tracked changes): https://verra.org/documents/vt0014-estimating-organic-carbon-stocks-using-digital-soil-mapping-tracked-changes
9. Verra – VM0047 v1.1: https://verra.org/methodologies/vm0047-afforestation-reforestation-and-revegetation-v1-1/
10. Verra – ICVCM approves VM0047 v1.1: https://verra.org/icvcm-approves-updated-version-of-verras-afforestation-reforestation-and-revegetation-methodology/
11. Verra – VM0048/VMD0055 ICVCM approval: https://verra.org/verras-redd-methodology-and-jurisdictional-and-nested-redd-framework-secure-icvcm-approval/
12. Verra – ICVCM clarification on JNR Scenario 1: https://verra.org/icvcm-clarifies-approval-of-verras-vm0048-to-include-jurisdictional-and-nested-redd-framework-scenario-1/
13. Verra – provisional deforestation risk maps: https://verra.org/verra-releases-provisional-versions-of-allocated-deforestation-risk-maps-for-use-with-new-redd-methodology/
14. ICVCM – three REDD+ methodologies approved: https://icvcm.org/integrity-council-approves-three-redd-methodologies/
15. Calyx Global – VM0048 baselines analysis: https://calyxglobal.com/research-hub/research/verras-consolidated-redd-methodology---part-2
16. Verra – VM0051 v1.1: https://verra.org/methodologies/vm0051-improved-management-in-rice-production-systems-v1-1/
17. Verra – Rice (VM0051) & landfill gas ICVCM approval: https://verra.org/verras-rice-cultivation-and-landfill-gas-methodologies-receive-icvcm-approval/
18. Verra – VM0051 approved under CORSIA: https://verra.org/verras-rice-methodology-approved-under-corsia/
19. Verra – minor revision to VM0051: https://verra.org/verra-publishes-minor-revision-to-rice-methodology-vm0051/
20. Verra – VM0033 v2.1: https://verra.org/methodologies/vm0033-methodology-for-tidal-wetland-and-seagrass-restoration-v2-1/
21. Verra – VM0033 major revision consultation: https://verra.org/consultation-revision-to-tidal-wetland-and-seagrass-restoration-methodology-vm0033/
22. Verra – VMD0051 tidal wetland monitoring module: https://verra.org/documents/vmd0051-methods-for-monitoring-carbon-stock-changes-in-tidal-wetland-restoration-and-conservation-activities-m-tw-v1-1
23. Verra – VM0044 v1.2 minor revision: https://verra.org/verra-publishes-minor-revision-to-biochar-methodology/
24. Verra – VM0044 & VM0045 ICVCM approval: https://verra.org/verras-biochar-and-forest-management-approaches-endorsed-by-icvcm-as-high-integrity-solutions/
25. Verra – RFP VM0044 v2.0 expert review: https://verra.org/documents/rfp-for-meth-experts-m0226-v1/
26. Verra – AFOLU NPRT v4.2 PDF: https://verra.org/wp-content/uploads/2023/10/AFOLU-Non-Permanence-Risk-Tool-v4.2-FINAL.pdf
27. Verra – AFOLU NPRT v4.0 PDF (10% minimum): https://verra.org/wp-content/uploads/AFOLU_Non-Permanence_Risk-Tool_v4.0.pdf
28. Verra – Procedure for Applying the AFOLU NPRT v5.0 (12% minimum): https://verra.org/wp-content/uploads/2025/12/Procedure-for-Applying-the-AFOLU-Non-Permanence-Risk-Tool-v5.0.pdf
29. Verra – Updated NPRT release notes: https://verra.org/verra-releases-updated-afolu-non-permanence-risk-tool/
30. Verra – VCS Version 5 overview (rev. Jun/Sep 2026): https://verra.org/wp-content/uploads/2025/12/VCS-Version-5-Overview-of-Program-Updates-and-Effective-Date-revised-June-2026.pdf
31. Verra – VCS program details / v5 documents: https://verra.org/programs/verified-carbon-standard/vcs-program-details/
32. Verra – VCS Methodology Requirements v5.0: https://verra.org/documents/vcs-methodology-requirements-v5-0/
33. Verra – VCS program updates (uncertainty v4.2): https://verra.org/verra-releases-updates-to-vcs-program/
34. Verra – VCU labels (CCP, Article 6, CORSIA): https://verra.org/programs/verified-carbon-standard/verified-carbon-units-labels/
35. Verra – First CCP labels on Verra Registry: https://verra.org/first-icvcm-ccp-labels-now-active-on-the-verra-registry/
36. Verra – VCS under CORSIA: https://verra.org/programs/verified-carbon-standard/vcs-under-corsia/
37. Gold Standard – A/R GHG methodology revision page: https://globalgoals.goldstandard.org/?p=13880
38. Gold Standard – SOC Framework Methodology v1.0: https://dev-globalgoals.goldstandard.org/standards/402_V1.0_LUF_AGR_FM_Soil-Organic-Carbon-Framework-Methodolgy.pdf
39. Gold Standard – SOC model requirements consultation (Jan 2025): https://www.goldstandard.org/consultations/soil-organic-carbon-soc-model-requirements-and-guidelines-consultation-jan2025
40. Gold Standard – Rice methodology page: https://globalgoals.goldstandard.org/methane-emission-reduction-by-adjusted-water-management-practice-in-rice-cultivation/
41. Gold Standard – Rice methodology summary 2024: https://globalgoals.goldstandard.org/standards/Rice-methodology-Summary-2024.pdf
42. ICVCM – GS rice decision document (M47): https://icvcm.org/wp-content/uploads/2026/02/M47_GS_RICE_v1.0_2026.pdf
43. ICVCM – Board Observations, Rice: https://icvcm.org/wp-content/uploads/2026/02/Board-Observations_Rice-1.pdf
44. ICVCM – ARR, IFM, rice decisions (Feb 2026): https://icvcm.org/integrity-council-announces-assessment-decisions-on-reforestation-improved-forest-management-ifm-and-rice-cultivation-methodologies/
45. Gold Standard – Compliance Buffer T&Cs (20%): https://globalgoals.goldstandard.org/standards/T-PreReview_V1.0-Terms_and_Conditions.pdf
46. Gold Standard – Uncertainty requirements consultation: https://www.goldstandard.org/consultations/requirements-for-uncertainty-assessment-and-addressal-gs4gg-methodologies
47. Gold Standard – Impact Registry: https://goldstandard.org/impact-registry
48. Gold Standard – SDG Impact Tool rule update 2022: https://dev-globalgoals.goldstandard.org/standards/RU_2022-The-SDG-Impact-Tool_v2.pdf
49. Carbon Herald – GS Paris alignment / retroactivity: https://carbonherald.com/project-developers-warn-gold-standard-against-retroactive-climate-rules/
50. Puro.earth – Biochar Edition 2025 intro: https://puro.earth/insights/post/348-introduction-to-the-updated-methodology-biochar-edition-2025/
51. Puro.earth – Biochar Methodology Edition 2025 v2 PDF: https://7518557.fs1.hubspotusercontent-na1.net/hubfs/7518557/Puro%20Biochar%20Methodology%20-%20Edition%202025%20(version%202)%20-%20For%20Publication.pdf
52. Puro.earth – Advancing the science of biochar permanence: https://puro.earth/insights/post/biochar-permanence/
53. EU Commission – CRCF biochar workshop deck (Woolf permanence factor): https://climate.ec.europa.eu/system/files/2023-10/event_20231025_presentations_2_en.pdf
54. Puro.earth – ERW methodology update (Nov 2025): https://puro.earth/insights/post/353-puro-earth-launches-enhanced-rock-weathering-methodology-update/
55. ICVCM – Puro.earth CCP-Eligible: https://icvcm.org/?p=16102
56. Carbon Herald – Puro CCP eligibility / CORSIA context: https://carbonherald.com/puro-earth-gains-ccp-eligibility-under-icvcm-review/
57. Isometric – Biochar soil storage module v1.2: https://registry.isometric.com/module/biochar-storage-soil-environments/1.2
58. Isometric – Biochar protocol: https://registry.isometric.com/protocol/biochar
59. Isometric – Certified biochar protocol article: https://isometric.com/writing-articles/certified-protocol-for-biochar-production-and-storage
60. Isometric – CRCF biochar requirements module: https://registry.isometric.com/module/biochar-requirements-crcf/1.0
61. Isometric – Enhanced Weathering Agriculture protocol: https://registry.isometric.com/protocol/enhanced-weathering-agriculture
62. Isometric – Standard v2.0: https://isometric.com/writing-articles/isometric-certifies-version-2-0-of-the-standard
63. Isometric – Registry concepts (buffer pool): https://docs.isometric.com/registry/key-registry-concepts
64. Isometric – Rice methane protocol: https://isometric.com/writing-articles/a-new-protocol-for-reducing-methane-emissions-from-rice-farming
65. Isometric – Improved soil management protocol: https://isometric.com/writing-articles/a-new-protocol-for-improved-soil-management
66. Carbon Pulse – Isometric soil carbon protocol launch: https://carbon-pulse.com/530958/
67. Isometric – ICVCM approves mangrove protocol: https://isometric.com/writing-articles/icvcm-approves-isometrics-mangrove-restoration-protocol
68. ICVCM – Isometric mangrove decision (M49): https://icvcm.org/wp-content/uploads/2026/05/M49_ISM_Mangrove_v1.0_2026.pdf
69. ICVCM – six CDR methodologies approved: https://icvcm.org/integrity-council-approves-six-carbon-dioxide-removal-methodologies/
70. ICVCM – new batch of decisions: https://icvcm.org/integrity-council-announces-new-batch-of-assessment-decisions/
71. ICVCM – BCS, Cercarbono, Plan Vivo CCP-Eligible: https://icvcm.org/integrity-council-announces-ccp-eligible-program-decisions-for-biocarbon-standard-cercarbono-and-plan-vivo-pv-climate/
72. ICVCM – ACR IFM decision (M43): https://icvcm.org/wp-content/uploads/2025/08/M43_ACR_IFMUSnf_v2.1_2025.pdf
73. Verra – VM0045 v1.2: https://verra.org/methodologies/vm0045-improved-forest-management-using-dynamic-matched-baselines-from-national-forest-inventories-v1-2/
74. Verra – New ICVCM decisions (renewables rejected): https://verra.org/new-icvcm-methodology-decisions-announced/
75. ESG Today – ICVCM rejects renewable energy credits: https://www.esgtoday.com/icvcm-rejects-carbon-credits-based-on-renewable-energy/
76. Calyx Global – CCP label tracker: https://calyxglobal.com/research-hub/commentary/icvcm-ccp-label-tracker
77. ICAO – CORSIA Eligible Emissions Units (Apr 2026): https://www.icao.int/sites/default/files/environmental-protection/CORSIA/Documents/CORSIA%20Eligible%20Emissions%20Units/CORSIA-Eligible-Emissions-Units_April-2026.pdf
78. ICAO – CORSIA Eligible Emissions Units (Oct 2025): https://www.icao.int/sites/default/files/environmental-protection/CORSIA/CORSIA-Eligible-Emissions-Units_Oct2025.pdf
79. ICAO – TAB Recommendations Jan 2026: https://www.icao.int/sites/default/files/environmental-protection/CORSIA/TAB/2026/TAB-Recommendations_January-2026.pdf
80. ICAO – Council decision C.236 (Phase 2 programmes): https://www.icao.int/sites/default/files/about-icao/Council/Council%20Documentation/236/C-DECs/C.236.DEC_.03.EN_.pdf
81. Fastmarkets – TAB 2026 cycle, Isometric & T-VER: https://www.fastmarkets.com/insights/icao-invites-applicants-for-tab-2026-assessment-cycle-and-stricter-loa-requirements-to-affect-corsia-phase-2-supply/
82. Carbon Direct – CORSIA Phase 1: https://www.carbon-direct.com/insights/corsia-phase-1-credits-compliance-and-what-comes-next
83. Green Fuel Journal – CORSIA supply gap: https://www.greenfueljournal.com/post/corsia-eligible-emissions-units-2026-2028
84. UNFCCC – Article 6.4 methodologies page: https://unfccc.int/process-and-meetings/the-paris-agreement/article-6/article-64-pacm/methodologies
85. UNFCCC – Article 6.4 rules & regulations: https://unfccc.int/process-and-meetings/bodies/constituted-bodies/article-64-supervisory-body/rules-and-regulations
86. UNFCCC – A6.4-AMM-001 (SBM019): https://unfccc.int/sites/default/files/resource/A6.4-SBM019-A02.pdf
87. UNFCCC – Non-permanence & reversals standard (SBM018): https://unfccc.int/documents/650344
88. UNFCCC – Reversal Risk Assessment tool (SBM023 draft): https://unfccc.int/sites/default/files/resource/3.4_27_SBM023_MethTool_Reversal_Risk.pdf
89. UNFCCC – Transition of CDM activities: https://unfccc.int/es/node/630398
90. UNFCCC – PACM regional dialogue Apr 2026 (A6.4ER issuance): https://unfccc.int/sites/default/files/resource/Session_01_PACM.pdf
91. S&P Global – Removals & methodology standards adopted (Oct 2024): https://www.spglobal.com/commodity-insights/en/news-research/latest-news/energy-transition/101024-un-carbon-body-adopts-standards-on-removals-methodologies-in-bid-to-fast-track-article-64
92. UNFCCC – ETF GWP (5/CMA.3): https://unfccc.int/sites/default/files/resource/ETF_cma7.pdf
93. BEE – Methodologies and tools under Offset Mechanism: https://beeindia.gov.in/view_content.php?lid=571&lang=1
94. BEE – OM approved sectors, Offset Mechanism: https://beeindia.gov.in/sites/default/files/2024-10/OM%20for%20approved%20Sectors%20in%20Offset%20Mechanism%20under%20CCTS.PDF
95. Prayas – draft offset methodologies 2025: https://energy.prayaspune.org/images/pdf/Carbon-markets-offset-methodologies-draft-2025.pdf
96. DoLR – India Article 6 / Grid-India registry note: https://dolr.gov.in/sites/default/files/8%20CM-A6_221123_V1.pdf
97. KS&K – Detailed offset procedure under CCTS: https://ksandk.com/newsletter/ministry-of-power-introduces-detailed-offset-mechanism-within-the-carbon-credit-trading-scheme/
98. ICAP – CCTS compliance obligations / market portal: https://icapcarbonaction.com/en/news/compliance-obligations-under-indias-carbon-credit-trading-scheme-enter-force-seven-sectors
99. UNFCCC – India A6.4 Form AC-001: https://unfccc.int/sites/default/files/resource/A6.4_Form_AC-001_India.pdf
100. Carbon Pulse – India expands Art 6.2 list, adds 6.4 list: https://carbon-pulse.com/306856/
101. Sylvera – Q3 2025 data snapshot: https://www.sylvera.com/blog/q3-2025-carbon-data-snapshot
102. Sylvera – carbon offset price trends: https://www.sylvera.com/blog/carbon-offset-price
103. Carbonunits – credit quality 2026 buyer's guide: https://carbonunits.com/news/carbon-credit-quality-in-2026-a-buyers-guide
104. CarbonCredits.com – CCP-labelled credits 13% of supply / premium: https://carboncredits.com/high-integrity-carbon-credits-ccp-label-13-percent-new-supply/
105. Abatable – How the market values CCP credits: https://abatable.com/blog/how-does-the-market-value-ccp-carbon-credits
106. Carbon Pulse – Biochar supply tightens (Supercritical): https://carbon-pulse.com/548363/
107. Reccessary – CDR.fyi/OPIS durable CDR prices: https://www.reccessary.com/en/news/cdr-credit-prices-defy-expectations-market-gap-narrows
108. BeZero – rating scale: https://bezerocarbon.com/insights/the-bezero-carbon-rating-definition-and-rating-scale
109. MSCI – Carbon project ratings explained: https://www.msci.com/data-and-analytics/carbon-markets/understanding-carbon-markets/msci-carbon-project-ratings-explained
110. Regreener – Rating agencies compared (Calyx scale change): https://www.regreener.earth/blog/carbon-credit-rating-agencies-compared
111. Sylvera – ratings terminology: https://www.sylvera.com/internal-posts/sylvera-carbon-credit-ratings-terminology
112. NIES/WGIA – IPCC 2019 rice EF update (India session): https://web3.nies.go.jp/gio/wgia/jqjm1000000j7eam-att/2-6_Session_2_India.pdf
113. PMC – rice EF table citing IPCC 2019 Tables 5.12/5.13: https://pmc.ncbi.nlm.nih.gov/articles/PMC10406717/table/Tab2
114. CCAFS AgLEDx – paddy rice UNFCCC guidance: https://agledx.ccafs.cgiar.org/estimating-emissions/unfccc-guidance/paddy-rice/
115. GHG Management Institute – which methane GWP to use: https://ghginstitute.org/?p=29487
116. IPCC 2019 Refinement Vol. 4 (for direct verification): https://www.ipcc-nggip.iges.or.jp/public/2019rf/vol4.html
