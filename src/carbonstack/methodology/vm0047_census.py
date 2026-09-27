"""VM0047, census-based approach.

The sibling of `vm0047.py`. Same methodology, different instrument, and the
choice between them is not a preference -- it is dictated by what is planted.

The area-based approach reads a stocking index over a contiguous canopy. That
works for a block planting and fails completely for the pathway this project
leads with: trees on a paddy bund are a line of stems narrower than a 10 m
Sentinel-2 pixel. There is no canopy for an index to measure, and an index
that returns near zero over a thriving bund line is not a conservative
estimate, it is a wrong one.

So this path counts. Every planted stem is inventoried, a sample is measured,
survival is surveyed, and the plot's stock is the surviving stems times the
mean stem. What it refuses:

  * Crediting the survival point estimate. The lower bound of the survey
    interval is used, because the alternative claims trees the surveyor did
    not find.
  * Issuing against an unvetted performance benchmark. VM0047 re-derives the
    baseline from what comparable land actually did, and a benchmark nobody
    vetted turns every project into a high performer.
  * Crediting a planting that is failing. Below 70% survival the plot needs
    replacing, not a vintage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..agroforestry import BenchmarkProvider, CensusInventory
from ..audit import Calculation
from ..domain import Project
from .base import (
    Deduction,
    VintageResult,
    apply_deductions,
    uncertainty_deduction,
)


@dataclass
class VM0047Census:
    id = "VM0047"
    version = "v1.1"
    approach = "census-based"
    name = "Afforestation, Reforestation and Revegetation (census-based)"
    credits_soil_carbon = False

    benchmark: BenchmarkProvider = field(default_factory=BenchmarkProvider)
    buffer_fraction: float = 0.20
    buffer_basis: str = "non-permanence risk rating, VM0047 range 10-25%"
    leakage_fraction: float = 0.0
    leakage_basis: str = "no activity displacement identified"
    minimum_survival: float = 0.70

    def quantify(self, project: Project, *,
                 inventories: dict[str, CensusInventory],
                 prior_inventories: dict[str, CensusInventory] | None = None,
                 reporting_year: int) -> VintageResult:
        """Credit inventory growth net of the performance benchmark.

        Inventories are keyed by plot id. A plot without one contributes
        nothing: a census credits what was counted.
        """
        prior_inventories = prior_inventories or {}
        result = VintageResult(
            project_id=project.id,
            methodology=f"{self.id} {self.version} ({self.approach})",
            year=reporting_year, area_ha=0.0, gross_t=0.0)
        result.excluded_plots = project.eligibility_issues()
        result.warnings.extend(project.programme_issues())

        if not self.benchmark.is_vetted:
            result.warnings.append(
                f"performance benchmark comes from '{self.benchmark.name}', "
                f"which is not a Verra-vetted data service provider; no "
                f"issuance may rest on it")

        creditable = project.creditable_plot_ids()
        area = 0.0
        counted_area = 0.0
        stock_now = 0.0
        stock_prior = 0.0
        sigmas: list[float] = []
        uncounted: list[str] = []

        for plot_id in sorted(creditable):
            ha = project.plots[plot_id].area_ha
            area += ha

            inventory = inventories.get(plot_id)
            if inventory is None:
                uncounted.append(plot_id)
                continue

            for problem in inventory.survival.issues():
                result.warnings.append(problem)
            if inventory.survival.survival_rate < self.minimum_survival:
                result.warnings.append(
                    f"plot {plot_id}: survival "
                    f"{inventory.survival.survival_rate:.0%} is below the "
                    f"{self.minimum_survival:.0%} floor; excluded from this "
                    f"vintage and flagged for replanting")
                continue

            calc = Calculation(f"census stock, {plot_id} {reporting_year}",
                               "tCO2e")
            total, relative = inventory.stock(calc=calc)
            counted_area += ha
            stock_now += total
            sigmas.append(total * relative)

            before = prior_inventories.get(plot_id)
            if before is not None:
                stock_prior += before.stock()[0]

            if len(result.calculations) < 3:
                result.calculations.append(calc)

        if uncounted:
            result.warnings.append(
                f"{len(uncounted)} plot(s) have no census inventory and "
                f"contribute nothing: {', '.join(uncounted[:5])}"
                + (" ..." if len(uncounted) > 5 else ""))

        point = self.benchmark.benchmark_for(project_id=project.id,
                                             year=reporting_year)

        summary = Calculation(
            f"VM0047 census abatement, vintage {reporting_year}", "tCO2e")
        summary.cite("Verra VM0047 v1.1, census-based approach")
        summary.cite(f"performance benchmark: {point.provider}")

        summary.add("creditable area", area, "ha")
        summary.add("area with a census", counted_area, "ha",
                    "a census credits what was counted")
        summary.add("inventory stock, end of year", stock_now, "tCO2e")
        summary.add("inventory stock, start of year", stock_prior, "tCO2e")
        growth = summary.add("inventory growth", stock_now - stock_prior,
                             "tCO2e")
        baseline = summary.add(
            "performance benchmark growth",
            point.t_co2e_per_ha_yr * counted_area, "tCO2e",
            f"{point.t_co2e_per_ha_yr} tCO2e/ha/yr over {point.control_units} "
            f"matched control units")
        gross = summary.add("gross abatement", max(0.0, growth - baseline),
                            "tCO2e", "growth less benchmark, floored at zero")

        if growth <= baseline and counted_area > 0:
            result.warnings.append(
                "inventory growth did not exceed the performance benchmark -- "
                "no credits this vintage, and additionality is in question")

        relative = (math.sqrt(sum(s ** 2 for s in sigmas)) / stock_now
                    if stock_now > 0 and sigmas else 0.0)
        summary.add("relative uncertainty", relative, "fraction")

        deductions = [
            uncertainty_deduction(relative),
            Deduction("leakage", self.leakage_fraction, self.leakage_basis),
            Deduction("buffer pool", self.buffer_fraction, self.buffer_basis),
        ]
        net, applied = apply_deductions(gross, deductions)
        summary.finish(net)

        result.area_ha = area
        result.gross_t = gross
        result.relative_uncertainty = relative
        result.deductions = applied
        result.net_t = net
        result.calculations.append(summary)
        return result
