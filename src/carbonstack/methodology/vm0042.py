"""VM0042 - Improved Agricultural Land Management, and rice water management.

The bridge track. Structurally simpler than VM0047 -- abatement is a practice
adopted on an area, times an emission factor -- and financially far tighter:
model/carbon_model.py puts the whole developer margin on a cropland hectare at
about $6 a year, which is why adoption is scored from remote sensing rather
than established by visiting anyone.

Two properties of this implementation are deliberate and worth defending:

  Adoption is a probability, not a flag. A satellite sees a dry-down with some
  confidence, not a farmer's intention. Crediting the full hectare whenever
  confidence clears an arbitrary line is how a cropland project over-credits
  without anyone lying; multiplying by confidence is the honest version, and
  it makes better detection worth money.

  The emission factor is tiered explicitly. A project running IPCC Tier 1
  defaults gets a punitive uncertainty deduction here, exactly as it would at
  verification. Moving to a locally measured Tier 3 factor is therefore a
  visible line in the revenue model rather than a scientific nicety.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..audit import Calculation
from ..domain import Project
from ..remote_sensing import Provider
from .base import (
    Deduction,
    VintageResult,
    apply_deductions,
    reporting_date,
    uncertainty_deduction,
)

TIER_UNCERTAINTY = {
    1: 0.50,   # IPCC global default factor applied to a local field
    2: 0.30,   # country or region specific
    3: 0.12,   # locally measured, model based -- below the 15% allowance
}


@dataclass
class EmissionFactor:
    """Abatement per hectare per year for an adopted practice."""

    practice: str
    t_co2e_per_ha_yr: float
    tier: int = 1
    source: str = "IPCC default"

    @property
    def relative_uncertainty(self) -> float:
        return TIER_UNCERTAINTY.get(self.tier, 0.50)


# Defaults sized from the sources in docs/research/01-mitti-labs-and-varaha.md.
# Replace every one of these with a locally measured factor before issuance.
DEFAULT_FACTORS = {
    "awd": EmissionFactor(
        practice="awd",
        t_co2e_per_ha_yr=1.6,
        tier=1,
        source="Gold Standard AWM rice: 20-100 kg CH4/ha/season baseline, "
               "20-50% reduction, 28x GWP, two seasons",
    ),
    "direct_seeded_rice": EmissionFactor(
        practice="direct_seeded_rice", t_co2e_per_ha_yr=1.2, tier=1,
        source="VM0042 practice shift, conservative placeholder",
    ),
    "residue_retention": EmissionFactor(
        practice="residue_retention", t_co2e_per_ha_yr=0.9, tier=1,
        source="VM0042 soil organic carbon, conservative placeholder",
    ),
    "reduced_tillage": EmissionFactor(
        practice="reduced_tillage", t_co2e_per_ha_yr=0.8, tier=1,
        source="VM0042 soil organic carbon, conservative placeholder",
    ),
}


@dataclass
class VM0042:
    id = "VM0042"
    name = "Improved Agricultural Land Management (practice-based)"

    factors: dict[str, EmissionFactor] = field(
        default_factory=lambda: dict(DEFAULT_FACTORS)
    )
    buffer_fraction: float = 0.15
    buffer_basis: str = "soil carbon reversal risk"
    minimum_confidence: float = 0.5
    """Below this, a plot is not credited at all rather than credited fractionally.
    Weak detections are noise, and noise credited at 30% is still noise."""

    def quantify(self, project: Project, provider: Provider,
                 reporting_year: int) -> VintageResult:
        result = VintageResult(
            project_id=project.id,
            methodology=self.id,
            year=reporting_year,
            area_ha=0.0,
            gross_t=0.0,
        )
        result.excluded_plots = project.eligibility_issues()

        on = reporting_date(reporting_year)
        creditable = project.creditable_plot_ids()
        practice_by_plot = {
            e.plot_id: e.practice for e in project.enrollments
            if e.plot_id in creditable and e.enrolled_on.year <= reporting_year
        }

        gross = 0.0
        effective_area = 0.0
        enrolled_area = 0.0
        weighted_unc = 0.0
        unknown: set[str] = set()
        low_confidence = 0

        for plot_id, practice in sorted(practice_by_plot.items()):
            plot = project.plots[plot_id]
            ha = plot.area_ha
            enrolled_area += ha

            factor = self.factors.get(practice)
            if factor is None:
                unknown.add(practice)
                continue

            det = provider.retrieve(plot, "practice_adopted", on)
            confidence = det.value if det is not None else 0.0
            if confidence < self.minimum_confidence:
                low_confidence += 1
                continue

            abatement = ha * factor.t_co2e_per_ha_yr * confidence
            gross += abatement
            effective_area += ha * confidence
            weighted_unc += abatement * factor.relative_uncertainty

        for practice in sorted(unknown):
            result.warnings.append(
                f"no emission factor for practice {practice!r} -- those plots "
                f"contribute nothing; add a factor or correct the enrolment"
            )
        if low_confidence:
            result.warnings.append(
                f"{low_confidence} plot(s) below {self.minimum_confidence:.0%} "
                f"adoption confidence, excluded from this vintage"
            )

        rel_unc = (weighted_unc / gross) if gross > 0 else 0.0

        summary = Calculation(f"VM0042 abatement, vintage {reporting_year}", "tCO2e")
        summary.cite("Verra VM0042 v2.0, Improved Agricultural Land Management")
        for f in sorted({p: self.factors[p] for p in practice_by_plot.values()
                         if p in self.factors}.values(), key=lambda x: x.practice):
            summary.cite(f"{f.practice}: {f.t_co2e_per_ha_yr} tCO2e/ha/yr "
                         f"(Tier {f.tier}) -- {f.source}")

        summary.add("enrolled area", enrolled_area, "ha")
        summary.add("confidence-weighted area", effective_area, "ha",
                    "area x detected adoption probability")
        summary.add("gross abatement", gross, "tCO2e")
        summary.add("relative uncertainty", rel_unc, "fraction",
                    "abatement-weighted across emission factor tiers")

        deductions = [
            uncertainty_deduction(rel_unc),
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
