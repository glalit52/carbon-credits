"""Which standard, under which methodology, and what each one leaves you.

The research note on Mitti Labs and Varaha ends on a decision nobody can
defer: *pick a registry path early*. The same physical tonne issues as a
different number of credits, under a different label, at a different price,
depending on where it is registered -- and some routes are closed outright
by a rule that has nothing to do with carbon. This module puts those routes
side by side for one project so the choice is made on numbers.

Two disciplines run through it.

**Every rule carries how well it is known.** The facts here come from
docs/research/02-methodologies-and-standards.md, which was assembled from
search summaries of primary sources because the primary PDFs could not be
fetched. Each `Fact` is tagged `primary`, `secondary` or `unconfirmed`, and
the comparison prints the weakest tag that any route leans on. A buffer
percentage that is UNCONFIRMED is a question for the registry, not a
parameter -- and the output says so beside the number rather than in a
footnote.

**A blocker is not a discount.** A route that cannot issue -- Gold Standard
2026 vintages on a non-Paris-aligned methodology version, CORSIA eligibility
for a host country that has not listed the activity for authorisation -- is
reported as blocked with its reason, never as a smaller number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from .methodology.base import Deduction, apply_deductions, uncertainty_deduction


class Status(str, Enum):
    PRIMARY = "primary"           # stated on the standard's own domain
    SECONDARY = "secondary"       # trade press, consultancies, aggregators
    UNCONFIRMED = "unconfirmed"   # not found in any source; check before relying


_RANK = {Status.PRIMARY: 0, Status.SECONDARY: 1, Status.UNCONFIRMED: 2}


@dataclass(frozen=True)
class Fact:
    value: object
    status: Status
    source: str = ""

    def __str__(self) -> str:
        tag = "" if self.status is Status.PRIMARY else f" [{self.status.value}]"
        return f"{self.value}{tag}"


def P(v, src=""):
    return Fact(v, Status.PRIMARY, src)


def S(v, src=""):
    return Fact(v, Status.SECONDARY, src)


def U(v, src=""):
    return Fact(v, Status.UNCONFIRMED, src)


def weakest(facts: list[Fact]) -> Status:
    return max((f.status for f in facts), key=_RANK.__getitem__, default=Status.PRIMARY)


# ---------------------------------------------------------------------------
# Verra's AFOLU Non-Permanence Risk Tool
# ---------------------------------------------------------------------------

NPRT_THRESHOLDS = {"internal": 35, "external": 20, "natural": 35}
"""A project whose score in any category exceeds its threshold fails the tool
outright: no buffer rate is high enough. NPRT v4.2 [primary]."""

NPRT_MINIMUM = {
    "v4.0": P(0.10, "AFOLU NPRT v4.0"),
    "v4.2": U(0.10, "v4.1 raised minimums; the v4.2 floor was not retrieved"),
    "v5.0": P(0.12, "Procedure for Applying the AFOLU NPRT v5.0, 16 Dec 2025"),
}


@dataclass(frozen=True)
class NprtScore:
    """Category scores as the NPRT calculator produces them.

    This does not reproduce the tool's internal tables -- since 2024 Verra
    requires its digital calculator for that. It takes the category totals
    the calculator reports and applies the two rules that turn them into a
    buffer: the failure thresholds and the minimum.
    """

    internal: float
    external: float
    natural: float
    version: str = "v5.0"

    def failures(self) -> list[str]:
        out = []
        for cat, limit in NPRT_THRESHOLDS.items():
            score = getattr(self, cat)
            if score > limit:
                out.append(f"{cat} risk {score:g} exceeds the NPRT threshold of {limit}")
        return out

    @property
    def rating(self) -> Fact:
        """Buffer fraction: the summed score, rounded up, never under the floor."""
        floor = NPRT_MINIMUM[self.version]
        total = math.ceil(self.internal + self.external + self.natural) / 100.0
        return Fact(max(total, floor.value), floor.status, floor.source)


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------

class Pathway(str, Enum):
    RICE = "rice"
    SOIL = "soil"
    ARR = "arr"                     # afforestation, reforestation, agroforestry
    REDD = "redd"
    BLUE_CARBON = "blue_carbon"
    BIOCHAR = "biochar"
    ERW = "erw"


#: Credit category for pricing. Avoided methane and stored carbon do not sell
#: in the same market and are not priced as if they did.
CATEGORY = {
    Pathway.RICE: "avoidance_methane",
    Pathway.SOIL: "nbs_removal_soil",
    Pathway.ARR: "nbs_removal_arr",
    Pathway.REDD: "avoidance_redd",
    Pathway.BLUE_CARBON: "nbs_removal_arr",
    Pathway.BIOCHAR: "durable_cdr",
    Pathway.ERW: "durable_cdr",
}


@dataclass(frozen=True)
class Route:
    """One methodology under one standard."""

    id: str
    standard: str
    methodology: str
    version: Fact
    pathway: Pathway
    unit: str
    buffer: Fact                    # fraction, or "nprt" for a risk-scored buffer
    ccp: Fact                       # "approved" | "conditional" | "no decision" | "not eligible"
    corsia: Fact                    # "eligible" | "programme only" | "no"
    durability: Fact | None = None
    notes: tuple[str, ...] = ()
    blockers_by_country: tuple[tuple[str, str], ...] = ()
    paris_aligned_version_required_from: int | None = None

    @property
    def is_registry(self) -> bool:
        return self.standard not in {"CCTS (India)"}

    def facts(self) -> list[Fact]:
        out = [self.version, self.buffer, self.ccp, self.corsia]
        return out + ([self.durability] if self.durability else [])


_V = "Verra VCS"
_GS = "Gold Standard"

ROUTES: dict[str, Route] = {r.id: r for r in (
    # --- rice ------------------------------------------------------------
    Route("vcs-vm0051", _V, "VM0051 Improved Management in Rice Production Systems",
          P("v1.1 (active 14 Jul 2026; v1.0 inactive 1 Aug 2027)"), Pathway.RICE, "VCU",
          buffer=P(0.0, "CH4 reductions are not subject to buffer withholding"),
          ccp=P("approved", "Verra, 12 Aug 2026"),
          corsia=P("eligible", "ICAO TAB, Phase 1 & 2, with host-country authorisation; "
                               "'REDD+ countries' qualifier unconfirmed"),
          notes=("baseline reassessed every 5 years (v1.1)",
                 "simplified default-factor route for projects <= 60,000 tCO2e/yr",
                 "replaces CDM AMS-III.AU")),
    Route("gs-rice", _GS, "Methane Emission Reduction by Adjusted Water Management "
                          "Practice in Rice Cultivation",
          P("v1.0 (Jul 2023)"), Pathway.RICE, "VER",
          buffer=P(0.0, "CH4 is irreversible"),
          ccp=P("conditional", "ICVCM Jan/Feb 2026: additionality via activity "
                               "penetration only, plus a soil-carbon-loss rule"),
          corsia=S("programme only"),
          notes=("credits issued before the CCP decision do not qualify for the label",),
          paris_aligned_version_required_from=2026),
    Route("isometric-rice", "Isometric", "Rice methane protocol",
          S("certified May 2026"), Pathway.RICE, "credit",
          buffer=P(0.0, "CH4 is irreversible"),
          ccp=U("no decision"), corsia=S("programme only")),
    Route("ccts-ag04", "CCTS (India)", "BM AG04.002 improved rice cultivation",
          S("published ~Jun 2025"), Pathway.RICE, "CCC",
          buffer=P(0.0, "CH4 is irreversible"),
          ccp=P("not eligible", "domestic compliance-linked scheme"),
          corsia=P("no", "Indian Carbon Credit Certificates are domestic"),
          notes=("Grid-India registry, BEE administrator",
                 "a tonne issued here must not also be issued internationally")),

    # --- soil ------------------------------------------------------------
    Route("vcs-vm0042", _V, "VM0042 Improved Agricultural Land Management",
          P("v2.2 (active 21 Oct 2025; corrections 11 Jun 2026 mandatory)"),
          Pathway.SOIL, "VCU",
          buffer=Fact("nprt", Status.PRIMARY, "AFOLU NPRT"),
          ccp=P("approved", "condition: SOC not measured by digital soil mapping"),
          corsia=P("programme only"),
          durability=P("project longevity >= 40 years; baseline reassessed every 10"),
          notes=("v3.0 major revision consulted Feb-Mar 2026, not final",)),
    Route("gs-soc", _GS, "Soil Organic Carbon Framework Methodology",
          P("v1.0"), Pathway.SOIL, "VER",
          buffer=P(0.20, "Gold Standard compliance buffer, land use & forests"),
          ccp=U("no decision"), corsia=S("programme only"),
          paris_aligned_version_required_from=2026),
    Route("isometric-soil", "Isometric", "Improved Soil Management protocol",
          S("certified 15 Jul 2026, cropland module"), Pathway.SOIL, "credit",
          buffer=U("buffer pool, rate not retrieved"),
          ccp=U("no decision"), corsia=S("programme only")),

    # --- trees -----------------------------------------------------------
    Route("vcs-vm0047", _V, "VM0047 Afforestation, Reforestation and Revegetation",
          P("v1.1 (May 2025); v1.0 registration requests close 31 Dec 2026"),
          Pathway.ARR, "VCU",
          buffer=Fact("nprt", Status.PRIMARY, "AFOLU NPRT"),
          ccp=P("approved", "both versions"),
          corsia=P("programme only"),
          durability=P("AFOLU crediting period 20-100 years"),
          notes=("dynamic performance benchmark from matched controls",
                 "census-based approach for trees outside forests has no leakage deduction")),
    Route("gs-ar", _GS, "A/R GHG Requirements and methodology",
          S("revision in progress"), Pathway.ARR, "VER",
          buffer=P(0.20, "Gold Standard compliance buffer, land use & forests"),
          ccp=U("no decision"), corsia=S("programme only"),
          paris_aligned_version_required_from=2026),
    Route("isometric-reforestation", "Isometric", "Reforestation protocol",
          P("v1.1"), Pathway.ARR, "credit",
          buffer=U("buffer pool, rate not retrieved"),
          ccp=P("approved", "Feb 2026, no conditions"), corsia=S("programme only")),
    Route("ccts-fr05-002", "CCTS (India)", "BM FR05.002 A/R of lands except wetlands",
          P("approved"), Pathway.ARR, "CCC",
          buffer=U("not retrieved"),
          ccp=P("not eligible", "domestic scheme"), corsia=P("no")),

    # --- forests and coasts ----------------------------------------------
    Route("vcs-vm0048", _V, "VM0048 Reducing Emissions from Deforestation and "
                            "Forest Degradation, with VMD0055",
          P("v1.x"), Pathway.REDD, "VCU",
          buffer=Fact("nprt", Status.PRIMARY, "AFOLU NPRT"),
          ccp=P("approved", "legacy VM0006/7/9/15/37 can never carry the label"),
          corsia=P("programme only"),
          notes=("baseline allocated from jurisdictional deforestation risk maps",)),
    Route("vcs-vm0033", _V, "VM0033 Tidal Wetland and Seagrass Restoration",
          P("v2.1"), Pathway.BLUE_CARBON, "VCU",
          buffer=Fact("nprt", Status.PRIMARY, "AFOLU NPRT"),
          ccp=U("no decision"), corsia=P("programme only")),
    Route("isometric-mangrove", "Isometric", "Mangrove Restoration protocol",
          P("v1.0"), Pathway.BLUE_CARBON, "credit",
          buffer=U("buffer pool, rate not retrieved"),
          ccp=P("approved", "Apr/May 2026, first blue-carbon approval"),
          corsia=S("programme only")),
    Route("ccts-fr05-001", "CCTS (India)", "BM FR05.001 A/R of degraded mangrove habitats",
          P("approved"), Pathway.BLUE_CARBON, "CCC",
          buffer=U("not retrieved"), ccp=P("not eligible"), corsia=P("no")),

    # --- durable removals --------------------------------------------------
    Route("puro-biochar", "Puro.earth", "Biochar Methodology",
          P("Edition 2025 (12 Jun 2025)"), Pathway.BIOCHAR, "CORC",
          buffer=U("decay deduction in quantification; pooled buffer not retrieved"),
          ccp=P("no decision", "programme CCP-eligible Dec 2025; methodology not assessed"),
          corsia=S("no"),
          durability=P("CORC200+ with molar H/Corg < 0.7")),
    Route("isometric-biochar", "Isometric", "Biochar Production and Storage",
          P("v1.3"), Pathway.BIOCHAR, "credit",
          buffer=U("buffer pool under Isometric Standard v2.0, rate not retrieved"),
          ccp=P("approved", "v1.0"), corsia=S("programme only"),
          durability=P("200 years at H/Corg < 0.5, or 1,000 years on measured "
                       "random reflectance (Ro >= 2% inertinite)")),
    Route("vcs-vm0044", _V, "VM0044 Biochar Utilization in Soil and Non-Soil Applications",
          P("v1.2"), Pathway.BIOCHAR, "VCU",
          buffer=U("decay model and reversal risk; rate not retrieved"),
          ccp=P("approved", "v1.2"), corsia=P("programme only"),
          durability=U("~100-year decay basis")),
    Route("puro-erw", "Puro.earth", "Enhanced Rock Weathering",
          P("Edition 2025 (Nov 2025)"), Pathway.ERW, "CORC",
          buffer=U("not retrieved"),
          ccp=P("no decision"), corsia=S("no"),
          notes=("field measurement mandatory; one quantifying and one validating approach",)),
    Route("isometric-erw", "Isometric", "Enhanced Weathering in Agriculture",
          P("v1.2"), Pathway.ERW, "credit",
          buffer=U("buffer pool, rate not retrieved"),
          ccp=U("no decision"), corsia=S("programme only")),
)}


# Host-country context that closes a route regardless of methodology.
COUNTRY_NOTES: dict[str, list[Fact]] = {
    "India": [
        U("India's Article 6 activity lists (Feb 2023, updated 2024) do not appear to "
          "include agriculture or nature-based activities; without a Letter of "
          "Authorisation and corresponding adjustment no CORSIA claim is possible",
          "research note section 8"),
    ],
}

PRICE_USD: dict[str, tuple[Fact, Fact, Fact]] = {
    # (low, mid, high) per tonne, 2025-26 indications. All secondary.
    "avoidance_methane": (S(15.0), S(20.0), S(25.0)),
    "nbs_removal_soil": (S(10.0), S(25.0), S(60.0)),
    "nbs_removal_arr": (S(9.0), S(22.0), S(29.0)),
    "avoidance_redd": (S(2.0), S(6.0), S(8.5)),
    "durable_cdr": (S(100.0), S(177.0), S(250.0)),
}

CCP_PREMIUM = S(0.19, "MSCI Global CCP index vs broad VCM; ICVCM cites ~25%")


def routes_for(pathway: Pathway | str) -> list[Route]:
    pw = Pathway(pathway)
    return [r for r in ROUTES.values() if r.pathway is pw]


# ---------------------------------------------------------------------------
# Comparing routes for one project
# ---------------------------------------------------------------------------

@dataclass
class RouteOutcome:
    route: Route
    gross_t: float
    deductions: list[tuple[Deduction, float]]
    net_t: float
    price_usd: float | None
    revenue_usd: float | None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    leans_on: Status = Status.PRIMARY
    buffer_known: bool = True

    @property
    def issuable(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict:
        r = self.route
        return {
            "route": r.id, "standard": r.standard, "methodology": r.methodology,
            "version": str(r.version), "unit": r.unit,
            "ccp": str(r.ccp), "corsia": str(r.corsia),
            "durability": str(r.durability) if r.durability else None,
            "gross_t": round(self.gross_t, 3),
            "deductions": [{"name": d.name, "fraction": round(d.fraction, 4),
                            "basis": d.basis, "amount_t": round(a, 3)}
                           for d, a in self.deductions],
            "net_t": round(self.net_t, 3),
            "price_usd": self.price_usd,
            "revenue_usd": None if self.revenue_usd is None else round(self.revenue_usd, 2),
            "issuable": self.issuable,
            "net_is_upper_bound": not self.buffer_known,
            "blockers": self.blockers, "warnings": self.warnings,
            "leans_on": self.leans_on.value,
        }


@dataclass
class Comparison:
    pathway: Pathway
    gross_t: float
    relative_uncertainty: float
    vintage: int
    country: str
    outcomes: list[RouteOutcome]
    context: list[Fact] = field(default_factory=list)

    def ranked(self) -> list[RouteOutcome]:
        """Issuable routes with every deduction known, by revenue; then
        issuable routes whose buffer is unknown, whose net is only an upper
        bound and so cannot outrank a real number; then blocked ones."""
        def by_rev(xs):
            return sorted(xs, key=lambda o: -(o.revenue_usd or 0))
        known = by_rev(o for o in self.outcomes if o.issuable and o.buffer_known)
        bound = by_rev(o for o in self.outcomes if o.issuable and not o.buffer_known)
        return known + bound + [o for o in self.outcomes if not o.issuable]

    def render(self) -> str:
        lines = [
            f"{self.pathway.value} -- {self.gross_t:,.1f} tCO2e gross, "
            f"{self.relative_uncertainty:.0%} uncertainty, vintage {self.vintage}, "
            f"{self.country or 'country not given'}",
            "=" * 96,
            f"  {'route':<24}{'unit':<7}{'buffer':>8}{'unc.':>7}{'net t':>10}"
            f"{'$/t':>8}{'revenue $':>12}  {'CCP':<14}{'CORSIA':<15}",
        ]
        for o in self.ranked():
            buf = next((d.fraction for d, _ in o.deductions if d.name == "buffer pool"), 0.0)
            unc = next((d.fraction for d, _ in o.deductions if d.name == "uncertainty"), 0.0)
            price = f"{o.price_usd:,.0f}" if o.price_usd is not None else "-"
            rev = f"{o.revenue_usd:,.0f}" if o.revenue_usd is not None else "-"
            flag = "" if o.leans_on is Status.PRIMARY else f"  [{o.leans_on.value}]"
            bufs = f"{buf:>7.0%}" if o.buffer_known else f"{'?':>7}"
            net = f"{o.net_t:,.1f}" if o.buffer_known else f"<={o.net_t:,.1f}"
            lines.append(
                f"  {o.route.id:<24}{o.route.unit:<7}{bufs}{unc:>7.0%}"
                f"{net:>10}{price:>8}{rev:>12}  "
                f"{str(o.route.ccp.value):<14}{str(o.route.corsia.value):<15}{flag}")
            for b in o.blockers:
                lines.append(f"      BLOCKED: {b}")
            for w in o.warnings:
                lines.append(f"      ! {w}")
        for f in self.context:
            lines.append(f"  * {f}")
        lines.append("  [secondary]/[unconfirmed] marks a route whose numbers lean on a "
                     "fact not confirmed from the standard itself.")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "pathway": self.pathway.value, "gross_t": self.gross_t,
            "relative_uncertainty": self.relative_uncertainty,
            "vintage": self.vintage, "country": self.country,
            "routes": [o.to_dict() for o in self.ranked()],
            "context": [{"note": str(f.value), "status": f.status.value} for f in self.context],
        }


def compare(pathway: Pathway | str, *, gross_t: float, relative_uncertainty: float,
            vintage: int, country: str = "", nprt: NprtScore | None = None,
            paris_aligned: bool = False, wants_corsia: bool = False,
            price_point: int = 1, biochar_h_corg: float | None = None,
            biochar_random_reflectance: bool = False,
            include_domestic: bool = True) -> Comparison:
    """Every route for this pathway, with the same tonnes run through each.

    `gross_t` is what the methodology engine produced before deductions; the
    deductions here are the ones that differ by standard -- buffer and the
    uncertainty allowance -- applied in the same order the engine applies
    them. Price is the band's low, mid or high point (0, 1, 2), plus the CCP
    premium where the label is approved.
    """
    pw = Pathway(pathway)
    outcomes = []
    context = list(COUNTRY_NOTES.get(country, []))
    for route in routes_for(pw):
        if not include_domestic and not route.is_registry:
            continue
        if route.standard == "CCTS (India)" and country and country != "India":
            continue
        blockers: list[str] = []
        warnings: list[str] = []
        leaned = list(route.facts())

        # Buffer
        if route.buffer.value == "nprt":
            if nprt is None:
                rating = NPRT_MINIMUM["v5.0"]
                warnings.append(f"no NPRT score given; buffer taken at the v5.0 floor "
                                f"of {rating.value:.0%}, which is the best case")
            else:
                for f in nprt.failures():
                    blockers.append(f"fails the AFOLU NPRT: {f}")
                rating = nprt.rating
            buf_frac = float(rating.value)
            leaned.append(rating)
        elif isinstance(route.buffer.value, (int, float)):
            buf_frac = float(route.buffer.value)
        else:
            buf_frac = None
            warnings.append(f"buffer: {route.buffer.value}; net is an upper bound")

        # Standard-specific gates
        if route.paris_aligned_version_required_from and \
                vintage >= route.paris_aligned_version_required_from and not paris_aligned:
            blockers.append(
                f"{route.standard} requires a Paris-aligned methodology version for "
                f"{route.paris_aligned_version_required_from}+ vintages")
        if route.ccp.value == "conditional":
            warnings.append(f"CCP label is conditional: {route.ccp.source}")
        if wants_corsia and route.corsia.value != "eligible":
            blockers.append(f"not CORSIA-eligible ({route.corsia.value})")
        if wants_corsia and route.corsia.value == "eligible" and country in COUNTRY_NOTES:
            blockers.append(f"CORSIA needs a {country} Letter of Authorisation and "
                            f"corresponding adjustment; see the country note")
            leaned.extend(COUNTRY_NOTES[country])
        if pw is Pathway.BIOCHAR:
            blockers.extend(_biochar_gate(route, biochar_h_corg, biochar_random_reflectance))

        deds = [uncertainty_deduction(relative_uncertainty)]
        if buf_frac:
            deds.append(Deduction("buffer pool", buf_frac,
                                  f"{route.standard} non-permanence buffer"))
        net, applied = apply_deductions(gross_t, deds)

        band = PRICE_USD[CATEGORY[pw]]
        price = float(band[price_point].value)
        leaned.append(band[price_point])
        if route.ccp.value == "approved":
            price *= 1 + float(CCP_PREMIUM.value)
            leaned.append(CCP_PREMIUM)
        if not route.is_registry:
            price = None                      # domestic price discovery has not happened
            warnings.append("no traded price yet for this domestic unit")
        revenue = None if price is None or blockers else net * price
        outcomes.append(RouteOutcome(route, gross_t, applied, net,
                                     None if price is None else round(price, 2),
                                     revenue, blockers, warnings, weakest(leaned),
                                     buffer_known=buf_frac is not None))
    if pw is Pathway.BIOCHAR:
        context.append(P("biochar gross must already be net of the standard's own "
                         "persistence / decay factor and life-cycle emissions; those "
                         "formulas differ by standard and are not applied here"))
    if relative_uncertainty > 1.0:
        context.append(P("relative uncertainty above 100% makes a VCS project ineligible",
                         "VCS uncertainty consultation outcome; final wording unconfirmed"))
    context.append(U("the uncertainty deduction here is the engine's 15% allowance rule "
                     "for every route; VCS v4.3+ uses a probability-of-exceedance method "
                     "and the Gold Standard land-use rule was not retrieved"))
    return Comparison(pw, gross_t, relative_uncertainty, vintage, country, outcomes, context)


def _biochar_gate(route: Route, h_corg: float | None, ro: bool) -> list[str]:
    if h_corg is None:
        return ["biochar H/Corg not given; every biochar route gates on it"]
    if route.id == "puro-biochar" and h_corg >= 0.7:
        return [f"H/Corg {h_corg:.2f} >= 0.7: not eligible for Puro CORC200+"]
    if route.id == "isometric-biochar" and h_corg >= 0.5 and not ro:
        return [f"H/Corg {h_corg:.2f} >= 0.5 and no random-reflectance measurement: "
                f"neither Isometric durability option is reachable"]
    return []
