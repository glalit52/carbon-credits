"""VM0051 - Improved Management in Rice Production Systems.

The purpose-built rice methodology, and the one this product should have been
using for paddy all along. The prototype quantified rice under VM0042, which
is an agricultural land management methodology that happens to cover rice;
VM0051 is written for it, replaces CDM AMS-III.AU in the VCS Program, and is
CORSIA eligible, which VM0042 is not.

Three properties separate it from VM0042, and each one changes an answer:

  **It credits methane, not soil carbon.** VM0051 does not credit soil organic
  carbon stock increases, and excludes practices that significantly reduce
  SOC. A project that wants the soil pool must use VM0042 instead -- so one
  hectare of paddy cannot carry both a VM0051 methane claim and a VM0042 soil
  claim. `stacking.py` enforces that; this module refuses to be part of it.

  **Eligibility is narrow.** Irrigated lowland rice only. Upland, rainfed and
  deepwater systems are excluded outright, because the project cannot control
  the water table, and controlling it is the intervention. A field without
  drainage control cannot deliver AWD however willing the farmer.

  **There is no buffer pool.** Non-permanence applies to carbon held in a
  stock that can be released. Avoided methane was never stored, so it cannot
  reverse: the tonne is abated at the moment the field is not flooded. The
  buffer fraction here therefore defaults to zero, which is not an oversight
  and is worth roughly a fifth of the credits against an ARR project.

Coefficients are placeholders and marked as such, as everywhere else in this
package. The structure, the eligibility rules and the deduction order are the
methodology's.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..audit import Calculation
from ..domain import Project, RiceEcosystem, WaterControl
from ..remote_sensing import Provider
from .base import (
    Deduction,
    VintageResult,
    apply_deductions,
    reporting_date,
    uncertainty_deduction,
)

CH4_GWP100 = 28.0
"""IPCC AR5, 100-year. Pinned here rather than imported from the feed so the
methodology owns its own constant -- a monitoring module changing its GWP must
not silently change what a vintage is worth."""

#: Relative uncertainty by IPCC tier, as in VM0042. A Tier 1 default applied
#: to a specific field is a guess with a wide error bar, and the deduction
#: above the 15% allowance is what that guess costs.
TIER_UNCERTAINTY = {1: 0.50, 2: 0.30, 3: 0.12}


@dataclass
class RiceEmissionFactor:
    """Baseline and project methane for one water regime, per ha per season.

    Both sides are explicit because VM0051 uses a dynamic baseline: the
    counterfactual is re-established rather than fixed once, so the baseline
    is data the project carries, not a constant buried in a formula.
    """

    baseline_ch4_kg_ha_season: float
    project_ch4_kg_ha_season: float
    seasons_per_year: float = 2.0
    tier: int = 1
    source: str = "IPCC default (placeholder)"

    def __post_init__(self) -> None:
        if self.project_ch4_kg_ha_season > self.baseline_ch4_kg_ha_season:
            raise ValueError(
                "project methane exceeds baseline: this is an increase, not an "
                "abatement, and VM0051 cannot credit it")

    @property
    def relative_uncertainty(self) -> float:
        return TIER_UNCERTAINTY.get(self.tier, 0.50)

    @property
    def abatement_t_co2e_ha_yr(self) -> float:
        delta_kg = (self.baseline_ch4_kg_ha_season
                    - self.project_ch4_kg_ha_season) * self.seasons_per_year
        return delta_kg * CH4_GWP100 / 1000.0

    @property
    def reduction_fraction(self) -> float:
        if self.baseline_ch4_kg_ha_season <= 0:
            return 0.0
        return 1 - self.project_ch4_kg_ha_season / self.baseline_ch4_kg_ha_season


@dataclass
class CommonPractice:
    """State-level AWD penetration, for the additionality test.

    VM0051 ties additionality to how widely the practice has already spread in
    the jurisdiction (assessed through VT0001). Past a threshold the practice
    is common, the counterfactual collapses, and the project is not additional
    no matter how well it is monitored. Verra rejected a run of rice projects
    in 2025 on exactly this point, so it is a gate rather than a note.
    """

    jurisdiction: str
    awd_penetration: float          # 0-1, share of rice area already on AWD
    threshold: float = 0.20
    source: str = "placeholder -- replace with a cited state-level survey"

    @property
    def is_common_practice(self) -> bool:
        return self.awd_penetration >= self.threshold


@dataclass
class VM0051:
    id = "VM0051"
    version = "v1.1"
    name = "Improved Management in Rice Production Systems"
    credits_soil_carbon = False
    """Read by the stacking engine. VM0051 leaves the soil pool alone, which
    is what makes a separate VM0042 soil claim on the same geometry double
    counting rather than a second product."""

    corsia_eligible = True

    factors: dict[str, RiceEmissionFactor] = field(default_factory=dict)
    common_practice: CommonPractice | None = None
    buffer_fraction: float = 0.0
    buffer_basis: str = (
        "none: avoided methane is not a stock and cannot reverse, so the "
        "AFOLU non-permanence buffer does not apply")
    leakage_fraction: float = 0.0
    leakage_basis: str = "no activity shifting identified"
    minimum_confidence: float = 0.5

    # -- eligibility --------------------------------------------------------

    def eligibility_issues(self, project: Project) -> dict[str, list[str]]:
        """Plots this methodology cannot credit, whatever the monitoring says.

        Run before quantification so an ineligible field is caught at
        enrolment rather than after a season of monitoring has been spent
        on it.
        """
        issues: dict[str, list[str]] = {}
        for e in project.enrollments:
            problems: list[str] = []

            if e.ecosystem is None:
                problems.append(
                    "rice ecosystem not recorded; VM0051 credits irrigated "
                    "lowland only")
            elif not e.ecosystem.vm0051_eligible:
                problems.append(
                    f"{e.ecosystem.value} rice is outside VM0051: the project "
                    f"cannot control the water table, and controlling it is "
                    f"the intervention")

            if e.water_control is None:
                problems.append("water control not recorded")
            elif not e.water_control.sufficient_for_awd:
                problems.append(
                    f"water control is {e.water_control.value}; AWD needs "
                    f"drainage control, not irrigation alone")

            if problems:
                issues[e.plot_id] = problems
        return issues

    def additionality_issues(self) -> list[str]:
        """Programme-level additionality, which fails for every plot at once."""
        if self.common_practice is None:
            return ["no common-practice assessment on record; VM0051 ties "
                    "additionality to AWD penetration in the jurisdiction"]
        cp = self.common_practice
        if cp.is_common_practice:
            return [f"AWD penetration in {cp.jurisdiction} is "
                    f"{cp.awd_penetration:.0%}, at or above the "
                    f"{cp.threshold:.0%} common-practice threshold -- the "
                    f"project is not additional"]
        return []

    # -- quantification -----------------------------------------------------

    def quantify(self, project: Project, provider: Provider,
                 reporting_year: int) -> VintageResult:
        result = VintageResult(
            project_id=project.id, methodology=f"{self.id} {self.version}",
            year=reporting_year, area_ha=0.0, gross_t=0.0)

        # Eligibility is the union of the project's own gates and this
        # methodology's. A plot blocked by either is not creditable.
        blocked = dict(project.eligibility_issues())
        for plot_id, problems in self.eligibility_issues(project).items():
            blocked.setdefault(plot_id, []).extend(problems)
        result.excluded_plots = blocked
        result.warnings.extend(project.programme_issues())

        additionality = self.additionality_issues()
        if additionality:
            result.warnings.extend(additionality)
            summary = Calculation(f"VM0051 abatement, vintage {reporting_year}",
                                  "tCO2e")
            summary.cite("Verra VM0051 v1.1, Improved Management in Rice "
                         "Production Systems")
            summary.add("gross abatement", 0.0, "tCO2e",
                        "withheld: additionality not established")
            summary.finish(0.0)
            result.calculations.append(summary)
            return result

        on = reporting_date(reporting_year)
        creditable = {e.plot_id for e in project.enrollments} - set(blocked)

        gross = 0.0
        enrolled_area = 0.0
        effective_area = 0.0
        weighted_unc = 0.0
        unknown: set[str] = set()
        low_confidence = 0

        for e in sorted(project.enrollments, key=lambda x: x.plot_id):
            if e.plot_id not in creditable or e.enrolled_on.year > reporting_year:
                continue
            ha = project.plots[e.plot_id].area_ha
            enrolled_area += ha

            factor = self.factors.get(e.practice)
            if factor is None:
                unknown.add(e.practice)
                continue

            det = provider.retrieve(project.plots[e.plot_id], "practice_adopted", on)
            confidence = det.value if det is not None else 0.0
            if confidence < self.minimum_confidence:
                low_confidence += 1
                continue

            abatement = ha * factor.abatement_t_co2e_ha_yr * confidence
            gross += abatement
            effective_area += ha * confidence
            weighted_unc += abatement * factor.relative_uncertainty

        for practice in sorted(unknown):
            result.warnings.append(
                f"no rice emission factor for practice {practice!r} -- those "
                f"plots contribute nothing")
        if low_confidence:
            result.warnings.append(
                f"{low_confidence} plot(s) below {self.minimum_confidence:.0%} "
                f"water-regime detection confidence, excluded from this vintage")

        rel_unc = (weighted_unc / gross) if gross > 0 else 0.0

        summary = Calculation(f"VM0051 abatement, vintage {reporting_year}", "tCO2e")
        summary.cite("Verra VM0051 v1.1, Improved Management in Rice "
                     "Production Systems (replaces CDM AMS-III.AU)")
        summary.cite("Additionality assessed through VT0001; common practice "
                     + (self.common_practice.source if self.common_practice else "n/a"))
        for practice in sorted({e.practice for e in project.enrollments
                                if e.practice in self.factors}):
            f_ = self.factors[practice]
            summary.cite(
                f"{practice}: baseline {f_.baseline_ch4_kg_ha_season} -> project "
                f"{f_.project_ch4_kg_ha_season} kg CH4/ha/season over "
                f"{f_.seasons_per_year} season(s), Tier {f_.tier} -- {f_.source}")

        summary.add("enrolled area", enrolled_area, "ha")
        summary.add("confidence-weighted area", effective_area, "ha",
                    "area x detected water-regime confidence")
        if self.common_practice:
            summary.add("AWD penetration in the jurisdiction",
                        self.common_practice.awd_penetration, "fraction",
                        f"{self.common_practice.jurisdiction}, threshold "
                        f"{self.common_practice.threshold:.0%}")
        summary.add("global warming potential", CH4_GWP100, "x",
                    "CH4 over 100 years, IPCC AR5")
        summary.add("gross abatement", gross, "tCO2e")
        summary.add("relative uncertainty", rel_unc, "fraction",
                    "abatement-weighted across emission factor tiers")

        deductions = [
            uncertainty_deduction(rel_unc),
            Deduction("leakage", self.leakage_fraction, self.leakage_basis),
            Deduction("buffer pool", self.buffer_fraction, self.buffer_basis),
        ]
        net, applied = apply_deductions(gross, deductions)
        summary.finish(net)

        result.area_ha = enrolled_area
        result.gross_t = gross
        result.relative_uncertainty = rel_unc
        result.deductions = applied
        result.net_t = net
        result.calculations.append(summary)
        return result


#: Sized from the Gold Standard AWM rice range (20-100 kg CH4/ha/season
#: baseline, 20-50% reduction) pending locally measured flux. Replace before
#: issuance -- at Tier 1 this costs 35% of gross to the uncertainty deduction.
DEFAULT_RICE_FACTORS = {
    "awd": RiceEmissionFactor(
        baseline_ch4_kg_ha_season=78.0,
        project_ch4_kg_ha_season=45.0,
        seasons_per_year=2.0,
        tier=1,
        source="placeholder from published AWD ranges; replace with measured flux"),
}
