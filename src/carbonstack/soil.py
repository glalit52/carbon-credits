"""Soil organic carbon: sampling, equivalent soil mass, and model validation.

The soil pathway under VM0042 is the one place in this product where a number
cannot come from a satellite. VM0042 requires physical cores, an accredited
lab, an equivalent-soil-mass correction, and -- where a biogeochemical model
does the quantifying between samplings -- calibration and validation under
**VMD0053**. None of that existed here, which is why the soil pillar was a
name on a roadmap rather than a pathway.

Two pieces of this module are where soil projects actually go wrong.

**Equivalent soil mass.** Compare SOC over a fixed *depth* and a field that
was merely compacted looks like it gained carbon: the same 30 cm now holds
more soil, so it holds more carbon, and nothing was sequestered. ESM compares
a fixed *mass* of fine earth instead, which is the only way the number means
what it claims. `esm_stock_change` refuses to report a fixed-depth change when
bulk density moved.

**Model validation.** A model that has never been tested against measured
cores is not evidence. VMD0053 asks for goodness of fit and a characterisation
of prediction error, and the error it finds becomes the uncertainty deduction
-- so a poorly validated model does not fail silently, it costs credits.

Equations here are standard soil science and are derived in the docstrings so
a reviewer can check them without a spreadsheet. Coefficients that stand in
for local data are marked, as everywhere else in this package.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from .audit import Calculation

CARBON_TO_CO2E = 44.0 / 12.0


# ---------------------------------------------------------------------------
# Cores
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SoilLayer:
    """One depth increment of a core, as the lab reports it."""

    top_cm: float
    bottom_cm: float
    soc_pct: float                  # % carbon by mass of fine earth
    bulk_density_g_cm3: float       # fine-earth bulk density
    coarse_fragment_frac: float = 0.0   # volumetric >2 mm, excluded from stock

    def __post_init__(self) -> None:
        if self.bottom_cm <= self.top_cm:
            raise ValueError(
                f"layer {self.top_cm}-{self.bottom_cm} cm has no thickness")
        if not 0 <= self.coarse_fragment_frac < 1:
            raise ValueError("coarse fragment fraction must be in [0, 1)")
        if self.bulk_density_g_cm3 <= 0:
            raise ValueError("bulk density must be positive")
        if self.soc_pct < 0:
            raise ValueError("soil carbon cannot be negative")

    @property
    def thickness_cm(self) -> float:
        return self.bottom_cm - self.top_cm

    @property
    def soil_mass_t_ha(self) -> float:
        """Fine-earth mass in this layer.

        A hectare is 10,000 m2. A layer d cm thick is d/100 m, so its volume is
        100*d m3 per hectare. Bulk density in g/cm3 equals t/m3, so the mass is
        100 * d * BD tonnes per hectare, less the coarse fragments.

        Sanity check: 30 cm at BD 1.3 gives 3,900 t/ha, which is the 0-3.9 Gg/ha
        range VM0042 works in.
        """
        return (100.0 * self.thickness_cm * self.bulk_density_g_cm3
                * (1 - self.coarse_fragment_frac))

    @property
    def soc_t_ha(self) -> float:
        """Carbon in this layer.

        mass * (soc_pct / 100), which reduces to
        soc_pct * BD * thickness * (1 - coarse), i.e. 1% C at BD 1.3 over
        30 cm is 39 t C/ha.
        """
        return self.soil_mass_t_ha * self.soc_pct / 100.0


@dataclass
class SoilCore:
    """One sampling location at one point in time."""

    plot_id: str
    sampled_on: date
    lab_reference: str
    layers: list[SoilLayer]
    stratum: str = ""

    def __post_init__(self) -> None:
        ordered = sorted(self.layers, key=lambda x: x.top_cm)
        for a, b in zip(ordered, ordered[1:]):
            if b.top_cm < a.bottom_cm - 1e-9:
                raise ValueError(
                    f"layers overlap at {b.top_cm} cm in core {self.plot_id}")
        self.layers = ordered

    @property
    def issues(self) -> list[str]:
        """Why a verifier would set this core aside."""
        problems: list[str] = []
        if not self.lab_reference.strip():
            problems.append(
                "no lab reference: an unattributable result is not evidence")
        if not self.layers:
            problems.append("core has no layers")
        if self.layers and self.layers[0].top_cm > 0:
            problems.append(
                f"core starts at {self.layers[0].top_cm} cm, missing the "
                f"surface layer where most change happens")
        return problems

    @property
    def max_depth_cm(self) -> float:
        return self.layers[-1].bottom_cm if self.layers else 0.0

    def soc_t_ha(self, to_depth_cm: float | None = None) -> float:
        """Fixed-depth SOC stock. Use ESM for any comparison over time."""
        total = 0.0
        for layer in self.layers:
            if to_depth_cm is None or layer.bottom_cm <= to_depth_cm:
                total += layer.soc_t_ha
            elif layer.top_cm < to_depth_cm:       # partial layer
                frac = (to_depth_cm - layer.top_cm) / layer.thickness_cm
                total += layer.soc_t_ha * frac
        return total

    def soil_mass_t_ha(self, to_depth_cm: float | None = None) -> float:
        total = 0.0
        for layer in self.layers:
            if to_depth_cm is None or layer.bottom_cm <= to_depth_cm:
                total += layer.soil_mass_t_ha
            elif layer.top_cm < to_depth_cm:
                frac = (to_depth_cm - layer.top_cm) / layer.thickness_cm
                total += layer.soil_mass_t_ha * frac
        return total

    def cumulative_profile(self) -> list[tuple[float, float]]:
        """(cumulative soil mass t/ha, cumulative SOC t/ha) down the core."""
        profile = [(0.0, 0.0)]
        mass = soc = 0.0
        for layer in self.layers:
            mass += layer.soil_mass_t_ha
            soc += layer.soc_t_ha
            profile.append((mass, soc))
        return profile


# ---------------------------------------------------------------------------
# Equivalent soil mass
# ---------------------------------------------------------------------------

def soc_at_equivalent_mass(core: SoilCore, reference_mass_t_ha: float, *,
                           calc: Calculation | None = None) -> float:
    """SOC held in the first `reference_mass_t_ha` tonnes of fine earth.

    Linear interpolation of the cumulative mass-carbon profile. VM0042 permits
    spline approaches too; linear is the conservative choice and is what a
    verifier can reproduce by hand from the layer table.

    Raises if the core does not reach the reference mass, because extrapolating
    past the bottom of a core invents carbon nobody measured.
    """
    profile = core.cumulative_profile()
    total_mass = profile[-1][0]
    if reference_mass_t_ha > total_mass + 1e-6:
        raise ValueError(
            f"core {core.plot_id} sampled to {total_mass:,.0f} t/ha of soil but "
            f"the reference mass is {reference_mass_t_ha:,.0f} t/ha -- sample "
            f"deeper rather than extrapolating")

    for (m0, c0), (m1, c1) in zip(profile, profile[1:]):
        if reference_mass_t_ha <= m1 + 1e-9:
            if m1 - m0 <= 0:
                soc = c0
            else:
                frac = (reference_mass_t_ha - m0) / (m1 - m0)
                soc = c0 + frac * (c1 - c0)
            if calc is not None:
                calc.add("reference soil mass", reference_mass_t_ha, "t/ha")
                calc.add("SOC at equivalent mass", soc, "t C/ha",
                         f"interpolated between {m0:,.0f} and {m1:,.0f} t/ha")
            return soc
    return profile[-1][1]


@dataclass
class StockChange:
    """A SOC change, and whether it survives the ESM correction."""

    plot_id: str
    baseline_soc_t_ha: float
    monitoring_soc_t_ha: float
    reference_mass_t_ha: float
    fixed_depth_change_t_ha: float
    bulk_density_change_pct: float
    calculation: Calculation
    warnings: list[str] = field(default_factory=list)

    @property
    def change_t_ha(self) -> float:
        return self.monitoring_soc_t_ha - self.baseline_soc_t_ha

    @property
    def change_t_co2e_ha(self) -> float:
        return self.change_t_ha * CARBON_TO_CO2E

    @property
    def compaction_artefact_t_ha(self) -> float:
        """How much of a fixed-depth reading was density, not carbon.

        The number that stops a compacted field being sold as a sequestering
        one. Reported rather than hidden, because it is usually the difference
        between a credit and no credit.
        """
        return self.fixed_depth_change_t_ha - self.change_t_ha


def esm_stock_change(baseline: SoilCore, monitoring: SoilCore, *,
                     reference_mass_t_ha: float | None = None,
                     compare_depth_cm: float = 30.0) -> StockChange:
    """SOC change between two samplings, on an equivalent soil mass basis.

    Compare a fixed depth instead and a field that was merely compacted reads
    as having gained carbon: the same 30 cm now holds more soil, so it holds
    more carbon, and nothing was sequestered. The reference mass defaults to
    the baseline's own mass over the comparison depth, which is the usual
    choice and keeps the baseline unadjusted.
    """
    if baseline.plot_id != monitoring.plot_id:
        raise ValueError(
            f"cores are from different plots: {baseline.plot_id} and "
            f"{monitoring.plot_id}")
    if monitoring.sampled_on <= baseline.sampled_on:
        raise ValueError(
            "the monitoring core is not later than the baseline core")

    calc = Calculation(f"SOC change on {baseline.plot_id}, equivalent soil mass",
                       "t C/ha")
    calc.cite("Verra VM0042 v2.x, soil organic carbon on an equivalent soil "
              "mass basis; VM0042 Soil Sampling and Analysis Handbook")

    ref = (reference_mass_t_ha
           if reference_mass_t_ha is not None
           else baseline.soil_mass_t_ha(compare_depth_cm))

    calc.add("comparison depth", compare_depth_cm, "cm")
    base_soc = soc_at_equivalent_mass(baseline, ref)
    calc.add("baseline SOC at reference mass", base_soc, "t C/ha",
             f"sampled {baseline.sampled_on}, lab {baseline.lab_reference}")
    mon_soc = soc_at_equivalent_mass(monitoring, ref)
    calc.add("monitoring SOC at reference mass", mon_soc, "t C/ha",
             f"sampled {monitoring.sampled_on}, lab {monitoring.lab_reference}")

    change = calc.add("SOC change (ESM)", mon_soc - base_soc, "t C/ha")

    fixed = (monitoring.soc_t_ha(compare_depth_cm)
             - baseline.soc_t_ha(compare_depth_cm))
    calc.add("SOC change (fixed depth, for contrast)", fixed, "t C/ha",
             "not creditable: a denser soil holds more carbon in the same "
             "depth without sequestering any")

    base_bd = baseline.soil_mass_t_ha(compare_depth_cm) / (100.0 * compare_depth_cm)
    mon_bd = monitoring.soil_mass_t_ha(compare_depth_cm) / (100.0 * compare_depth_cm)
    bd_change = (mon_bd / base_bd - 1) * 100 if base_bd else 0.0
    calc.add("bulk density change", bd_change, "%")
    calc.add("carbon dioxide equivalent", change * CARBON_TO_CO2E, "tCO2e/ha",
             f"x {CARBON_TO_CO2E:.4f} (44/12)")
    calc.finish(change)

    warnings: list[str] = []
    for core in (baseline, monitoring):
        warnings += [f"{core.sampled_on}: {p}" for p in core.issues]
    if abs(bd_change) > 5:
        warnings.append(
            f"bulk density moved {bd_change:+.1f}% between samplings; the "
            f"fixed-depth reading would have been wrong by "
            f"{fixed - (mon_soc - base_soc):+,.2f} t C/ha")

    return StockChange(
        plot_id=baseline.plot_id, baseline_soc_t_ha=base_soc,
        monitoring_soc_t_ha=mon_soc, reference_mass_t_ha=ref,
        fixed_depth_change_t_ha=fixed, bulk_density_change_pct=bd_change,
        calculation=calc, warnings=warnings)


# ---------------------------------------------------------------------------
# Sampling design
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Stratum:
    """One homogeneous block of the project area."""

    name: str
    area_ha: float
    soc_std_dev_t_ha: float      # prior, from a pilot or a soil map
    existing_samples: int = 0

    def __post_init__(self) -> None:
        if self.area_ha <= 0:
            raise ValueError(f"stratum {self.name} has no area")
        if self.soc_std_dev_t_ha < 0:
            raise ValueError(f"stratum {self.name} has negative variance")


@dataclass
class SamplingDesign:
    """How many cores, and where, to hit a target precision.

    VM0042 requires stratified random sampling because SOC varies with soil
    type, topography and management history, and an unstratified sample of a
    varied landscape buys precision nobody can afford.

    The allocation is Neyman's: samples go where the variance and the area
    are, not evenly. A uniform allocation over these strata needs materially
    more cores for the same precision, and cores are the dominant cost of a
    soil project.
    """

    strata: list[Stratum]
    target_margin_t_ha: float = 2.0     # half-width of the confidence interval
    confidence: float = 0.90
    comparison_depth_cm: float = 30.0
    expected_bd_decrease_pct: float = 10.0
    """How much bulk density might fall over the crediting period.

    This is a sampling-design input, not a detail. Equivalent soil mass
    compares a fixed mass of fine earth, so if management loosens the soil --
    which is what good management does -- a monitoring core taken to the
    comparison depth holds *less* mass than the baseline did, and the
    reference mass becomes unreachable. The core cannot be extended after the
    fact, so the depth has to carry headroom from the first sampling."""

    @property
    def z(self) -> float:
        # Two-sided normal deviate. 90% is the VCS convention for uncertainty.
        return {0.80: 1.2816, 0.90: 1.6449, 0.95: 1.9600}.get(
            round(self.confidence, 2), 1.6449)

    @property
    def total_area_ha(self) -> float:
        return sum(s.area_ha for s in self.strata)

    def required_samples(self) -> dict[str, int]:
        """Neyman allocation across the strata, at least 3 cores each.

        n = (z * sum(W_h * S_h) / E)^2, then split in proportion to W_h * S_h.
        The floor of 3 exists because a stratum with one or two cores has no
        usable variance of its own, whatever the formula says.
        """
        total = self.total_area_ha
        weighted = [(s, (s.area_ha / total) * s.soc_std_dev_t_ha)
                    for s in self.strata]
        sum_ws = sum(w for _, w in weighted)
        if sum_ws <= 0 or self.target_margin_t_ha <= 0:
            return {s.name: 3 for s in self.strata}

        n_total = (self.z * sum_ws / self.target_margin_t_ha) ** 2
        out: dict[str, int] = {}
        for stratum, w in weighted:
            share = w / sum_ws if sum_ws else 0
            out[stratum.name] = max(3, math.ceil(n_total * share))
        return out

    @property
    def recommended_sampling_depth_cm(self) -> float:
        """Sample this deep to keep the reference mass reachable later.

        A 10% fall in bulk density over the crediting period needs roughly
        11% more depth to hold the same mass of fine earth. Sampling only to
        the comparison depth is the single most common way a soil project
        finds, years later, that its monitoring cores cannot be compared with
        its baseline at all.
        """
        headroom = 1.0 / (1.0 - self.expected_bd_decrease_pct / 100.0)
        return round(self.comparison_depth_cm * headroom + 4.999, -1)

    def plan(self) -> dict:
        required = self.required_samples()
        outstanding = {
            s.name: max(0, required[s.name] - s.existing_samples)
            for s in self.strata
        }
        return {
            "strata": len(self.strata),
            "total_area_ha": round(self.total_area_ha, 3),
            "confidence": self.confidence,
            "target_margin_t_ha": self.target_margin_t_ha,
            "required_samples": required,
            "outstanding_samples": outstanding,
            "total_required": sum(required.values()),
            "total_outstanding": sum(outstanding.values()),
            "comparison_depth_cm": self.comparison_depth_cm,
            "recommended_sampling_depth_cm": self.recommended_sampling_depth_cm,
            "depth_note": (
                f"sample to {self.recommended_sampling_depth_cm:.0f} cm, not "
                f"{self.comparison_depth_cm:.0f} cm: equivalent soil mass needs "
                f"headroom if bulk density falls, and a core cannot be "
                f"extended after the fact"),
        }


# ---------------------------------------------------------------------------
# VMD0053 model validation
# ---------------------------------------------------------------------------

@dataclass
class ModelValidation:
    """Model performance against measured cores, per VMD0053.

    VMD0053 asks for goodness of fit and a characterisation of prediction
    error, and that error is what the uncertainty deduction is built from. So
    a model nobody validated does not fail quietly -- it either cannot be used
    or it is charged for at the punitive end.

    Held-out pairs only. Scoring a model on the cores it was fitted to reports
    how well it memorised them, which is not the question.
    """

    model_name: str
    model_version: str
    pairs: list[tuple[float, float]]     # (measured t C/ha, modelled t C/ha)
    held_out: bool = True

    #: VMD0053 expects validation against an independent set. A model scored on
    #: its training data is reported but never accepted.
    MIN_PAIRS = 10

    @property
    def n(self) -> int:
        return len(self.pairs)

    @property
    def mean_measured(self) -> float:
        return sum(m for m, _ in self.pairs) / self.n if self.n else 0.0

    @property
    def bias_t_ha(self) -> float:
        """Mean error. A model that is wrong in one direction is worse than one
        that is noisy, because the error does not average out over a portfolio."""
        if not self.n:
            return 0.0
        return sum(p - m for m, p in self.pairs) / self.n

    @property
    def rmse_t_ha(self) -> float:
        if not self.n:
            return 0.0
        return math.sqrt(sum((p - m) ** 2 for m, p in self.pairs) / self.n)

    @property
    def r_squared(self) -> float:
        if self.n < 2:
            return 0.0
        mean = self.mean_measured
        ss_tot = sum((m - mean) ** 2 for m, _ in self.pairs)
        ss_res = sum((m - p) ** 2 for m, p in self.pairs)
        return 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    @property
    def relative_uncertainty(self) -> float:
        """Prediction error as a fraction of the mean measured stock.

        This is the number that reaches the deduction. Bias is added to the
        random error rather than averaged with it, because a systematic offset
        does not cancel across plots the way scatter does.
        """
        mean = self.mean_measured
        if mean <= 0:
            return 1.0
        return (self.rmse_t_ha + abs(self.bias_t_ha)) / mean

    def issues(self) -> list[str]:
        problems: list[str] = []
        if not self.held_out:
            problems.append(
                f"{self.model_name} was scored on its training data; VMD0053 "
                f"requires an independent validation set")
        if self.n < self.MIN_PAIRS:
            problems.append(
                f"{self.n} validation pair(s); VMD0053 performance cannot be "
                f"characterised on fewer than {self.MIN_PAIRS}")
        if not self.model_version.strip():
            problems.append(
                f"{self.model_name} has no version pinned; a model result that "
                f"cannot be reproduced is not evidence")
        return problems

    @property
    def acceptable(self) -> bool:
        return not self.issues()

    def report(self) -> Calculation:
        calc = Calculation(
            f"VMD0053 validation of {self.model_name} {self.model_version}",
            "fraction")
        calc.cite("Verra VMD0053 v2.x, Model Calibration, Validation and "
                  "Uncertainty Guidance for biogeochemical modelling")
        calc.add("validation pairs", float(self.n), "cores",
                 "held out" if self.held_out else "TRAINING DATA -- not acceptable")
        calc.add("mean measured stock", self.mean_measured, "t C/ha")
        calc.add("bias", self.bias_t_ha, "t C/ha",
                 "positive means the model over-predicts")
        calc.add("RMSE", self.rmse_t_ha, "t C/ha")
        calc.add("R squared", self.r_squared, "")
        calc.finish(calc.add(
            "relative uncertainty", self.relative_uncertainty, "fraction",
            "(RMSE + |bias|) / mean measured; bias is added rather than "
            "averaged because a systematic offset does not cancel across plots"))
        return calc
