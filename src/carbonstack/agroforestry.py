"""Trees: species allometry, census inventory, and survival.

The area-based VM0047 path in `methodology/vm0047.py` credits a stocking index
over a contiguous planting. It is the wrong instrument for the pathway this
project actually leads with. Trees on a paddy bund are a line of stems a few
metres wide -- narrower than a 10 m Sentinel-2 pixel, and nothing like a
canopy the stocking index can measure. VM0047 anticipates this and offers a
**census-based** approach: count the trees, measure a sample, and carry the
inventory.

Three things separate a defensible census from a spreadsheet of stem counts.

**Species-specific allometry.** A generic stand fit carries about 25% error
before the satellite adds any, and that error is deducted from every vintage.
A registry-accepted, species- and region-specific equation is the tree
project's equivalent of a Tier 3 emission factor: the same trees, more
credits. The Chave et al. (2014) pantropical form is implemented because a
verifier will recognise it, alongside per-species power laws.

**Survival, measured rather than assumed.** Planted is not established. ARR
projects fail on mortality nobody counted, and a survival rate asserted from
the planting record is the single easiest thing for a verifier to reject.
Survival here comes from a sample with a confidence interval, and the lower
bound is what gets credited.

**Sampling error that reaches the deduction.** A census of 40 stems out of
4,000 is an estimate. Its error belongs in the uncertainty, not in a footnote.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from .audit import Calculation

CARBON_FRACTION = 0.47
CO2_PER_C = 44.0 / 12.0


# ---------------------------------------------------------------------------
# Species and their allometry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Species:
    """One species, with the equation that turns a measurement into biomass.

    `equation` selects the form:

      "chave2014"  AGB(kg) = 0.0673 * (rho * D^2 * H)^0.976
                   The pantropical form. Needs diameter, height and wood
                   density, and is what a field crew's callipers produce.

      "power_dbh"  AGB(kg) = a * D^b
                   A local, species-specific fit. Preferred where one exists,
                   because it is what a registry accepts as Tier 3 equivalent.

      "power_height" AGB(kg) = a * H^b
                   Height only, for stems measured from the air. Weakest of
                   the three and carries the widest error, which is the point:
                   remote sensing alone is cheaper and is charged for.
    """

    name: str
    equation: str = "chave2014"
    wood_density_g_cm3: float = 0.60
    a: float = 0.0
    b: float = 0.0
    root_shoot: float = 0.27
    relative_error: float = 0.25
    source: str = "generic placeholder -- replace with a local fit"
    region: str = ""

    def __post_init__(self) -> None:
        if self.equation not in ("chave2014", "power_dbh", "power_height"):
            raise ValueError(f"unknown allometric form {self.equation!r}")
        if self.equation != "chave2014" and self.b <= 0:
            raise ValueError(
                f"{self.name}: a power law needs a positive exponent b")
        if self.wood_density_g_cm3 <= 0:
            raise ValueError(f"{self.name}: wood density must be positive")

    @property
    def is_locally_calibrated(self) -> bool:
        """A local fit is the tree project's Tier 3. Generic is not."""
        return "placeholder" not in self.source.lower()

    def agb_kg(self, *, dbh_cm: float | None = None,
               height_m: float | None = None) -> float:
        """Above-ground biomass of one stem, in kilograms."""
        if self.equation == "chave2014":
            if dbh_cm is None or height_m is None:
                raise ValueError(
                    f"{self.name}: Chave 2014 needs both diameter and height")
            if dbh_cm <= 0 or height_m <= 0:
                return 0.0
            return 0.0673 * (self.wood_density_g_cm3 * dbh_cm ** 2
                             * height_m) ** 0.976
        if self.equation == "power_dbh":
            if dbh_cm is None:
                raise ValueError(f"{self.name}: needs a diameter")
            return self.a * dbh_cm ** self.b if dbh_cm > 0 else 0.0
        if height_m is None:
            raise ValueError(f"{self.name}: needs a height")
        return self.a * height_m ** self.b if height_m > 0 else 0.0

    def co2e_kg(self, **kw) -> float:
        """One stem's carbon dioxide equivalent, roots included."""
        agb = self.agb_kg(**kw)
        return agb * (1 + self.root_shoot) * CARBON_FRACTION * CO2_PER_C


#: Species used by the pilots. Every one is a placeholder until a local fit
#: replaces it, and `is_locally_calibrated` says so.
SPECIES = {
    "grevillea_robusta": Species(
        name="Grevillea robusta", equation="chave2014",
        wood_density_g_cm3=0.58, root_shoot=0.27,
        source="Chave et al. 2014 pantropical form with a generic wood "
               "density -- placeholder until a Kenyan highland fit is sourced",
        region="Kenya, Central Highlands"),
    "melia_dubia": Species(
        name="Melia dubia", equation="chave2014",
        wood_density_g_cm3=0.35, root_shoot=0.27,
        source="Chave et al. 2014 pantropical form -- placeholder pending an "
               "Indian farm-forestry fit",
        region="India, southern peninsula"),
    "tectona_grandis": Species(
        name="Tectona grandis", equation="chave2014",
        wood_density_g_cm3=0.55, root_shoot=0.27,
        source="Chave et al. 2014 pantropical form -- placeholder",
        region="India"),
}


# ---------------------------------------------------------------------------
# Survival
# ---------------------------------------------------------------------------

@dataclass
class SurvivalSurvey:
    """A sample of planted stems, checked for whether they are alive.

    Planted is not established. A survival rate asserted from the planting
    record is the easiest thing in an ARR project for a verifier to reject, so
    this is a measurement with an interval and the **lower bound** is what
    gets credited.
    """

    plot_id: str
    surveyed_on: date
    stems_planted: int
    stems_sampled: int
    stems_alive: int
    surveyor: str = ""

    def __post_init__(self) -> None:
        if self.stems_sampled <= 0:
            raise ValueError("a survey with no sampled stems is not a survey")
        if self.stems_alive > self.stems_sampled:
            raise ValueError(
                f"{self.plot_id}: {self.stems_alive} alive out of "
                f"{self.stems_sampled} sampled")
        if self.stems_sampled > self.stems_planted:
            raise ValueError(
                f"{self.plot_id}: sampled more stems than were planted")

    @property
    def survival_rate(self) -> float:
        return self.stems_alive / self.stems_sampled

    @property
    def standard_error(self) -> float:
        """Binomial standard error, with the finite population correction.

        A census of every planted stem has no sampling error, and the
        correction is what says so rather than charging for uncertainty that
        was not incurred.
        """
        p = self.survival_rate
        n = self.stems_sampled
        N = self.stems_planted
        if n >= N:
            return 0.0
        se = math.sqrt(max(p * (1 - p), 1e-12) / n)
        return se * math.sqrt((N - n) / (N - 1)) if N > 1 else se

    def survival_lower_bound(self, confidence: float = 0.90) -> float:
        """The conservative rate. Crediting the point estimate claims half a
        survey's worth of trees that may not be there."""
        z = {0.80: 1.2816, 0.90: 1.6449, 0.95: 1.9600}.get(
            round(confidence, 2), 1.6449)
        return max(0.0, self.survival_rate - z * self.standard_error)

    @property
    def surviving_stems(self) -> int:
        return int(self.stems_planted * self.survival_lower_bound())

    def issues(self) -> list[str]:
        problems: list[str] = []
        if not self.surveyor.strip():
            problems.append(
                f"{self.plot_id}: survey has no surveyor recorded")
        coverage = self.stems_sampled / self.stems_planted
        if coverage < 0.05:
            problems.append(
                f"{self.plot_id}: {coverage:.1%} of stems sampled; below 5% "
                f"the interval is too wide to credit against")
        if self.survival_rate < 0.70:
            problems.append(
                f"{self.plot_id}: survival {self.survival_rate:.0%} -- below "
                f"70% the planting needs replacing, not crediting")
        return problems

    @property
    def needs_replanting(self) -> bool:
        return self.survival_rate < 0.70


# ---------------------------------------------------------------------------
# Census inventory
# ---------------------------------------------------------------------------

@dataclass
class StemMeasurement:
    """One measured stem in the inventory sample."""

    species_key: str
    dbh_cm: float | None = None
    height_m: float | None = None


@dataclass
class CensusInventory:
    """A census-based inventory for one plot at one time.

    VM0047's census approach: count every planted stem, measure a sample, and
    scale. Right for scattered trees -- a bund line, a boundary planting, a
    few stems per field -- where a stocking index has nothing to measure.
    """

    plot_id: str
    measured_on: date
    survival: SurvivalSurvey
    sample: list[StemMeasurement] = field(default_factory=list)
    species: dict[str, Species] = field(default_factory=lambda: dict(SPECIES))

    def __post_init__(self) -> None:
        unknown = {m.species_key for m in self.sample} - set(self.species)
        if unknown:
            raise ValueError(
                f"{self.plot_id}: no allometry for species "
                f"{', '.join(sorted(unknown))}")

    @property
    def mean_co2e_per_stem_kg(self) -> float:
        if not self.sample:
            return 0.0
        total = sum(
            self.species[m.species_key].co2e_kg(dbh_cm=m.dbh_cm,
                                                height_m=m.height_m)
            for m in self.sample)
        return total / len(self.sample)

    @property
    def stem_sampling_error(self) -> float:
        """Relative standard error of the mean stem, from the sample spread.

        A sample of forty stems standing for four thousand is an estimate, and
        its error belongs in the deduction rather than a footnote.
        """
        n = len(self.sample)
        if n < 2:
            return 1.0
        values = [self.species[m.species_key].co2e_kg(dbh_cm=m.dbh_cm,
                                                      height_m=m.height_m)
                  for m in self.sample]
        mean = sum(values) / n
        if mean <= 0:
            return 1.0
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        return (math.sqrt(variance / n)) / mean

    @property
    def allometry_error(self) -> float:
        """Sample-weighted allometric error across the species present."""
        if not self.sample:
            return 1.0
        return sum(self.species[m.species_key].relative_error
                   for m in self.sample) / len(self.sample)

    @property
    def uses_local_allometry(self) -> bool:
        return bool(self.sample) and all(
            self.species[m.species_key].is_locally_calibrated
            for m in self.sample)

    def stock(self, *, calc: Calculation | None = None) -> tuple[float, float]:
        """Plot carbon stock in tCO2e, and its relative uncertainty.

        Surviving stems times mean stem carbon. The survival lower bound is
        used rather than the point estimate, so the claim is the conservative
        one.
        """
        c = calc or Calculation(f"census stock, {self.plot_id}", "tCO2e")
        c.cite("Verra VM0047 v1.1, census-based approach")
        c.cite("Chave et al. (2014) pantropical allometry where no local fit "
               "is available")

        c.add("stems planted", float(self.survival.stems_planted), "stems")
        c.add("stems sampled for survival", float(self.survival.stems_sampled),
              "stems")
        c.add("survival rate", self.survival.survival_rate, "fraction")
        lower = c.add("survival, lower 90% bound",
                      self.survival.survival_lower_bound(), "fraction",
                      "credited conservatively; the point estimate would claim "
                      "trees the survey did not find")
        stems = c.add("surviving stems credited",
                      float(self.survival.surviving_stems), "stems")
        per_stem = c.add("mean carbon per stem",
                         self.mean_co2e_per_stem_kg, "kgCO2e",
                         f"from {len(self.sample)} measured stem(s)")

        total = stems * per_stem / 1000.0
        sampling = c.add("stem sampling error", self.stem_sampling_error,
                         "fraction")
        allometry = c.add("allometric error", self.allometry_error, "fraction",
                          "local fit" if self.uses_local_allometry
                          else "GENERIC equation -- a local fit would cost "
                               "less in deductions")
        survival_err = (self.survival.standard_error
                        / self.survival.survival_rate
                        if self.survival.survival_rate > 0 else 1.0)
        c.add("survival sampling error", survival_err, "fraction")

        combined = math.sqrt(sampling ** 2 + allometry ** 2 + survival_err ** 2)
        c.add("combined uncertainty", combined, "fraction",
              "independent sources added in quadrature")
        c.finish(total)
        return total, combined


@dataclass
class BenchmarkPoint:
    """A performance benchmark observation from a data service provider."""

    year: int
    t_co2e_per_ha_yr: float
    provider: str
    control_units: int = 0


class BenchmarkProvider:
    """Where the dynamic performance benchmark comes from.

    VM0047 re-derives the baseline at each verification from what comparable,
    uncredited land actually did, and Verra vets the providers who supply it
    -- Sylvera, Kanop and Chloris Geospatial among them. Buying that is
    cheaper and more defensible than building it, so this is an adapter, not
    an implementation.

    The placeholder below returns a constant and says so. A benchmark quietly
    set near zero turns every project into a high performer, which is the
    failure VM0047 exists to close, so the provider name travels with the
    number into the audit trail.
    """

    name = "placeholder"

    def __init__(self, t_co2e_per_ha_yr: float = 0.6):
        self.value = t_co2e_per_ha_yr

    def benchmark_for(self, *, project_id: str, year: int) -> BenchmarkPoint:
        return BenchmarkPoint(
            year=year, t_co2e_per_ha_yr=self.value,
            provider="placeholder -- replace with a Verra-vetted data service "
                     "provider (Sylvera, Kanop, Chloris Geospatial)",
            control_units=0)

    @property
    def is_vetted(self) -> bool:
        """Only a vetted provider's benchmark can support an issuance."""
        return False
