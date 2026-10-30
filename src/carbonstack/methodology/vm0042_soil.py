"""VM0042's measure-and-model soil pathway.

VM0042 credits two pools: rice methane and soil organic carbon. The
practice-based path in `vm0042.py` handles the first. This handles the second,
and it is shaped differently on purpose.

Every other pathway in this package takes a `Provider` and asks it for a
number. Soil cannot: the number comes from a physical core, an accredited lab
and, between samplings, a biogeochemical model that VMD0053 requires somebody
to have validated. Forcing that through a satellite-retrieval interface would
be the wrong abstraction, so this class takes cores and a validation report
directly and is kept out of the provider-driven registry.

What it will not do:

  * Credit a fixed-depth stock change. Compaction alone can manufacture one,
    so every change is computed on an equivalent soil mass basis.
  * Use an unvalidated model. VMD0053 asks for goodness of fit and a
    characterised prediction error; without one there is no defensible
    uncertainty, and a project that cannot state its uncertainty gets the
    punitive default rather than a pass.
  * Quietly average a systematic bias away. Model bias is added to the random
    error, because an offset does not cancel across plots.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..audit import Calculation
from ..domain import Project
from ..soil import CARBON_TO_CO2E, ModelValidation, SoilCore, esm_stock_change
from .base import (
    Deduction,
    VintageResult,
    apply_deductions,
    uncertainty_deduction,
)

#: Applied when no validated model backs the quantification. VMD0053's point
#: is that unvalidated model output is not evidence; this is what assuming it
#: anyway costs.
UNVALIDATED_MODEL_UNCERTAINTY = 0.75


@dataclass
class VM0042Soil:
    id = "VM0042"
    version = "v2.2"
    pathway = "soil (measure and model)"
    name = "Improved Agricultural Land Management -- soil organic carbon"
    credits_soil_carbon = True

    validation: ModelValidation | None = None
    buffer_fraction: float = 0.15
    buffer_basis: str = (
        "soil carbon is a stock and can be released by a single tillage pass, "
        "so the non-permanence buffer applies")
    leakage_fraction: float = 0.0
    leakage_basis: str = "no activity shifting identified"
    compare_depth_cm: float = 30.0

    def quantify(self, project: Project, *,
                 baseline_cores: dict[str, SoilCore],
                 monitoring_cores: dict[str, SoilCore],
                 reporting_year: int) -> VintageResult:
        """Credit the SOC change between two samplings, ESM-corrected.

        Cores are keyed by plot id. A plot with no paired cores contributes
        nothing and is reported -- soil is credited on what was measured, not
        on what was assumed about the plots nobody visited.
        """
        result = VintageResult(
            project_id=project.id,
            methodology=f"{self.id} {self.version} ({self.pathway})",
            year=reporting_year, area_ha=0.0, gross_t=0.0)
        result.excluded_plots = project.eligibility_issues()
        result.warnings.extend(project.programme_issues())

        creditable = project.creditable_plot_ids()

        model_unc = UNVALIDATED_MODEL_UNCERTAINTY
        if self.validation is None:
            result.warnings.append(
                "no VMD0053 model validation on record; the punitive default "
                f"uncertainty of {UNVALIDATED_MODEL_UNCERTAINTY:.0%} applies")
        else:
            problems = self.validation.issues()
            if problems:
                result.warnings.extend(problems)
            else:
                model_unc = self.validation.relative_uncertainty
            result.calculations.append(self.validation.report())

        gross = 0.0
        measured_area = 0.0
        enrolled_area = 0.0
        unpaired: list[str] = []

        for plot_id in sorted(creditable):
            ha = project.plots[plot_id].area_ha
            enrolled_area += ha

            base = baseline_cores.get(plot_id)
            mon = monitoring_cores.get(plot_id)
            if base is None or mon is None:
                unpaired.append(plot_id)
                continue

            try:
                change = esm_stock_change(
                    base, mon, compare_depth_cm=self.compare_depth_cm)
            except ValueError as exc:
                result.warnings.append(f"plot {plot_id}: {exc}")
                continue

            result.warnings.extend(f"plot {plot_id}: {w}" for w in change.warnings)
            measured_area += ha

            # A loss is a loss. Crediting only the gains and ignoring the
            # losses is how a portfolio drifts upward without anyone lying.
            gross += change.change_t_co2e_ha * ha
            if len(result.calculations) < 4:
                result.calculations.append(change.calculation)

        if unpaired:
            result.warnings.append(
                f"{len(unpaired)} plot(s) have no paired baseline and "
                f"monitoring core and contribute nothing: "
                f"{', '.join(unpaired[:5])}"
                + (" ..." if len(unpaired) > 5 else ""))

        summary = Calculation(
            f"VM0042 soil organic carbon, vintage {reporting_year}", "tCO2e")
        summary.cite("Verra VM0042 v2.x, improved agricultural land "
                     "management, soil organic carbon pool")
        summary.cite("Verra VMD0053 v2.x, model calibration, validation and "
                     "uncertainty guidance")
        summary.cite("Equivalent soil mass basis; fixed-depth comparison is "
                     "not creditable because compaction alone produces one")

        summary.add("enrolled area", enrolled_area, "ha")
        summary.add("area with paired cores", measured_area, "ha",
                    "soil is credited on what was measured")
        summary.add("carbon to CO2e factor", CARBON_TO_CO2E, "x", "44/12")
        gross = summary.add("gross stock change", gross, "tCO2e",
                            "losses included, not only gains")
        summary.add("model uncertainty", model_unc, "fraction",
                    "from VMD0053 validation" if self.validation
                    and not self.validation.issues()
                    else "punitive default: no accepted validation")

        if gross <= 0:
            result.warnings.append(
                "no net soil carbon gain this vintage; nothing to credit")
            gross = max(0.0, gross)

        deductions = [
            uncertainty_deduction(model_unc),
            Deduction("leakage", self.leakage_fraction, self.leakage_basis),
            Deduction("buffer pool", self.buffer_fraction, self.buffer_basis),
        ]
        net, applied = apply_deductions(gross, deductions)
        summary.finish(net)

        result.area_ha = enrolled_area
        result.gross_t = gross
        result.relative_uncertainty = model_unc
        result.deductions = applied
        result.net_t = net
        result.calculations.append(summary)
        return result
