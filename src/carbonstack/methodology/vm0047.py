"""VM0047 - Afforestation, Reforestation and Revegetation.

The methodology that matters for the estate track, and the first nature-based
one built around remote sensing. Two things make it different from the ARR
methodologies it replaces, and both are implemented here:

  1. The baseline is not argued in a project document and then frozen. It is
     re-derived at every verification from a dynamic performance benchmark --
     what comparable land actually did over the same period. A project only
     earns the difference between its own growth and the benchmark's.

  2. The stocking index, a remotely sensed measure of vegetative cover, is the
     quantity that drives both the additionality test and the crediting
     baseline.

This implementation covers the area-based approach. The census-based approach
(individual tree inventory) is a different quantification path and is not
implemented -- it is the right choice for sparse, high-value plantings and
should be added as a sibling class rather than a flag on this one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..audit import Calculation
from ..biomass import Allometry, co2e_per_ha
from ..domain import Project
from ..remote_sensing import Provider
from .base import (
    Deduction,
    VintageResult,
    apply_deductions,
    combine_uncertainty,
    reporting_date,
    uncertainty_deduction,
)


@dataclass
class PerformanceBenchmark:
    """What comparable, uncredited land did over the same period.

    In production this comes from a Verra-vetted data service provider over a
    matched control population. Holding it as an explicit object keeps the
    provenance visible: a benchmark quietly set to zero turns every project
    into a high performer, which is precisely the failure mode VM0047 exists
    to close.
    """

    t_co2e_per_ha_yr: float
    source: str = "placeholder - replace with a Verra-vetted data service provider"
    matched_control_n: int = 0

    def growth_for(self, area_ha: float) -> float:
        return self.t_co2e_per_ha_yr * area_ha


@dataclass
class VM0047:
    id = "VM0047"
    name = "Afforestation, Reforestation and Revegetation (area-based)"

    benchmark: PerformanceBenchmark = field(
        default_factory=lambda: PerformanceBenchmark(t_co2e_per_ha_yr=0.8)
    )
    allometry: Allometry = field(default_factory=Allometry)
    buffer_fraction: float = 0.20
    buffer_basis: str = "non-permanence risk rating, VM0047 range 10-25%"
    leakage_fraction: float = 0.0
    leakage_basis: str = "no activity displacement identified"

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

        now = reporting_date(reporting_year)
        prior = reporting_date(reporting_year - 1)

        stock_now = stock_prior = 0.0
        sigmas: list[float] = []
        area = 0.0

        for plot_id in sorted(project.creditable_plot_ids()):
            plot = project.plots[plot_id]
            ha = plot.area_ha

            h_now = provider.retrieve(plot, "canopy_height_m", now)
            h_prior = provider.retrieve(plot, "canopy_height_m", prior)
            if h_now is None:
                result.warnings.append(
                    f"plot {plot_id}: no canopy retrieval for {reporting_year}, excluded"
                )
                continue

            calc = Calculation(f"plot {plot_id} standing stock {reporting_year}",
                               "tCO2e/ha")
            per_ha_now, sigma_now = co2e_per_ha(
                h_now.value,
                allometry=self.allometry,
                height_uncertainty_m=h_now.uncertainty,
                calc=calc,
            )
            per_ha_prior = 0.0
            if h_prior is not None:
                per_ha_prior, _ = co2e_per_ha(
                    h_prior.value,
                    allometry=self.allometry,
                    height_uncertainty_m=h_prior.uncertainty,
                )

            if per_ha_now < per_ha_prior:
                result.warnings.append(
                    f"plot {plot_id}: standing stock fell "
                    f"{per_ha_prior - per_ha_now:,.1f} tCO2e/ha -- possible "
                    f"disturbance, confirm before issuing"
                )

            area += ha
            stock_now += per_ha_now * ha
            stock_prior += per_ha_prior * ha
            sigmas.append(sigma_now * ha)
            if len(result.calculations) < 3:   # keep a readable sample, not all of them
                result.calculations.append(calc)

        summary = Calculation(f"VM0047 abatement, vintage {reporting_year}", "tCO2e")
        summary.cite("Verra VM0047 v1.1 (June 2025), area-based approach")
        summary.cite(f"performance benchmark: {self.benchmark.source}")

        summary.add("creditable area", area, "ha")
        summary.add("standing stock, end of year", stock_now, "tCO2e")
        summary.add("standing stock, start of year", stock_prior, "tCO2e")
        project_growth = summary.add("project growth", stock_now - stock_prior, "tCO2e")

        baseline = summary.add(
            "performance benchmark growth",
            self.benchmark.growth_for(area),
            "tCO2e",
            f"{self.benchmark.t_co2e_per_ha_yr} tCO2e/ha/yr over "
            f"{self.benchmark.matched_control_n} matched control units",
        )
        gross = summary.add("gross abatement", max(0.0, project_growth - baseline),
                            "tCO2e", "project growth less benchmark; floored at zero")

        if project_growth <= baseline and area > 0:
            result.warnings.append(
                "project growth did not exceed the performance benchmark -- "
                "no credits this vintage, and additionality is in question"
            )

        rel_unc = combine_uncertainty(sigmas, stock_now) if stock_now else 0.0
        summary.add("relative uncertainty", rel_unc, "fraction")

        deductions = [
            uncertainty_deduction(rel_unc),
            Deduction("leakage", self.leakage_fraction, self.leakage_basis),
            Deduction("buffer pool", self.buffer_fraction, self.buffer_basis),
        ]
        net, applied = apply_deductions(gross, deductions)
        summary.finish(net)

        result.area_ha = area
        result.gross_t = gross
        result.relative_uncertainty = rel_unc
        result.deductions = applied
        result.net_t = net
        result.calculations.append(summary)
        return result
