"""Canopy height to CO2e, with the uncertainty carried through.

This is the chain the whole ARR product rests on:

    canopy height -> above-ground biomass -> total biomass -> carbon -> CO2e

Each step has a published coefficient and a real error bar. We propagate the
error rather than quoting a point estimate, because the methodology deducts
for uncertainty and a project that cannot state its uncertainty gets the
punitive default.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .audit import Calculation

# IPCC defaults. Override per project once local allometry exists -- that
# local equation is the "Tier 3" asset Mitti Labs built for rice, and the
# equivalent moat for a tree project.
CARBON_FRACTION = 0.47          # IPCC AFOLU default, dry matter to carbon
CO2_PER_C = 44.0 / 12.0         # molecular weight ratio
DEFAULT_ROOT_SHOOT = 0.27       # tropical/subtropical, broadleaf


@dataclass(frozen=True)
class Allometry:
    """AGB = a * H^b, in tonnes dry matter per hectare.

    Power-law height-to-biomass fits are the standard form for stand-level
    remote sensing. The defaults here are a generic humid-tropical stand fit
    and should be replaced with a locally calibrated equation before any
    issuance -- that replacement is a project milestone, not a refinement.
    """

    a: float = 1.00
    b: float = 1.85
    relative_error: float = 0.25   # 1 sigma, fraction of the estimate
    label: str = "generic agroforestry stand fit (placeholder)"

    def agb_t_per_ha(self, height_m: float) -> float:
        if height_m <= 0:
            return 0.0
        return self.a * (height_m ** self.b)


def co2e_per_ha(
    height_m: float,
    *,
    allometry: Allometry | None = None,
    root_shoot: float = DEFAULT_ROOT_SHOOT,
    height_uncertainty_m: float = 0.0,
    calc: Calculation | None = None,
) -> tuple[float, float]:
    """Standing CO2e per hectare and its 1-sigma uncertainty.

    Returns (co2e_t_per_ha, sigma_t_per_ha).
    """
    allo = allometry or Allometry()
    c = calc or Calculation("standing stock", "tCO2e/ha")

    c.add("canopy height", height_m, "m")
    if height_uncertainty_m:
        c.add("canopy height uncertainty (1 sigma)", height_uncertainty_m, "m")

    agb = c.add("above-ground biomass", allo.agb_t_per_ha(height_m), "t DM/ha",
                f"AGB = {allo.a} * H^{allo.b} -- {allo.label}")
    bgb = c.add("below-ground biomass", agb * root_shoot, "t DM/ha",
                f"root:shoot = {root_shoot}")
    total = c.add("total biomass", agb + bgb, "t DM/ha")
    carbon = c.add("carbon", total * CARBON_FRACTION, "t C/ha",
                   f"carbon fraction = {CARBON_FRACTION} (IPCC default)")
    co2e = c.add("carbon dioxide equivalent", carbon * CO2_PER_C, "tCO2e/ha",
                 f"x {CO2_PER_C:.4f} (44/12)")

    # Height error enters through the power law, so it is amplified by b.
    rel_from_height = (
        allo.b * height_uncertainty_m / height_m if height_m > 0 and height_uncertainty_m
        else 0.0
    )
    rel = math.sqrt(rel_from_height ** 2 + allo.relative_error ** 2)
    sigma = c.add("uncertainty (1 sigma)", co2e * rel, "tCO2e/ha",
                  f"height term {rel_from_height:.1%}, allometry term "
                  f"{allo.relative_error:.1%}, combined {rel:.1%}")

    c.cite("IPCC 2006 AFOLU Vol 4, carbon fraction and root:shoot defaults")
    c.finish(co2e)
    return co2e, sigma
