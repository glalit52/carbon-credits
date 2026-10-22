"""RothC-26.3: what a soil-carbon practice is expected to do, before cores say so.

A soil project needs a number long before its second round of cores exists.
The project description needs an ex-ante estimate, the offtake needs a
forward volume, and the farmer needs to be told what a practice change is
worth. Every serious soil methodology -- VM0042's measure-and-model approach,
the Gold Standard SOC framework -- lets that number come from a
biogeochemical model, provided the model is named, versioned and validated
(VMD0053). RothC is the model a verifier is most likely to recognise: five
pools, monthly, driven by temperature, rainfall, evaporation, clay and
carbon inputs, and nothing else.

That "nothing else" is the point and the limit. RothC has no tillage term, no
nitrogen and no crop growth, so it cannot credit reduced tillage at all and
it needs carbon inputs supplied from outside. This module says so on every
projection that leans on a practice RothC cannot see, rather than letting a
plausible number imply a mechanism the model does not have.

Equations follow Coleman & Jenkinson (1996, RothC-26.3 user guide, revised
2014). Every modifier is implemented as written there, so a reviewer can
check this against the guide line by line.

Initialisation is by the standard steady-state assumption: the baseline
management is taken to have held the soil at equilibrium, and the plant
input that produces the measured stock at equilibrium is solved for, exactly
rather than by a long spin-up. That assumption is stated in the derivation,
because a soil that is still losing carbon from a past land-use change is
not at equilibrium and the projection will flatter the project.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

from .audit import Calculation
from .connectors.weather import ClimateSeries, MonthlyWeather
from .methodology.base import uncertainty_deduction

CARBON_TO_CO2E = 44.0 / 12.0

K_DPM, K_RPM, K_BIO, K_HUM = 10.0, 0.3, 0.66, 0.02
"""Decomposition rate constants, per year (Coleman & Jenkinson 1996)."""

BIO_SHARE = 0.46
"""Of the carbon that does not leave as CO2, 46% goes to BIO and 54% to HUM."""

FYM_SPLIT = (0.49, 0.49, 0.02)
"""Farmyard manure enters as 49% DPM, 49% RPM, 2% HUM."""

PADDY_RATE_FACTOR = 0.2
"""Decomposition multiplier for a flooded month (Shirato & Yokozawa 2005,
paddy-modified RothC). Anaerobic soil decomposes about five times slower."""

DPM_RPM = {
    "crop": 1.44,           # agricultural crops and improved grassland
    "grassland": 0.67,      # unimproved grassland and scrub
    "woodland": 0.25,       # deciduous and tropical woodland
}


def temperature_modifier(temp_c: float) -> float:
    """a = 47.91 / (1 + exp(106.06 / (T + 18.27))). Zero below -18.27 C."""
    if temp_c <= -18.27:
        return 0.0
    return 47.91 / (1.0 + math.exp(106.06 / (temp_c + 18.27)))


def max_tsmd(clay_pct: float, depth_cm: float = 23.0, *, bare: bool = False) -> float:
    """Maximum topsoil moisture deficit, mm (negative).

    -(20 + 1.3 clay - 0.01 clay^2) for the 0-23 cm layer, scaled by depth.
    A bare soil dries less far -- the roots are not there to pull water
    up -- so its limit is the vegetated one divided by 1.8.
    """
    m = -(20.0 + 1.3 * clay_pct - 0.01 * clay_pct ** 2) * (depth_cm / 23.0)
    return m / 1.8 if bare else m


def moisture_modifier(acc_tsmd: float, max_deficit: float) -> float:
    """b = 1 until the deficit passes 44.4% of the maximum, then falls to 0.2."""
    if acc_tsmd >= 0.444 * max_deficit:
        return 1.0
    return 0.2 + 0.8 * (max_deficit - acc_tsmd) / (max_deficit - 0.444 * max_deficit)


def co2_fraction(clay_pct: float) -> float:
    """Share of decomposed carbon respired. x = 1.67 (1.85 + 1.60 e^(-0.0786 clay))."""
    x = 1.67 * (1.85 + 1.60 * math.exp(-0.0786 * clay_pct))
    return x / (x + 1.0)


def falloon_iom(total_soc_t_ha: float) -> float:
    """Inert organic matter from total SOC (Falloon et al. 1998): 0.049 SOC^1.139."""
    return 0.049 * total_soc_t_ha ** 1.139


# ---------------------------------------------------------------------------
# Management
# ---------------------------------------------------------------------------

EVEN = tuple([1 / 12] * 12)


@dataclass(frozen=True)
class Management:
    """What the land receives and how it is covered, month by month.

    `plant_input_t_c_ha` is None for the baseline, which is solved from the
    measured stock. A project is described relative to it.
    """

    name: str
    plant_input_t_c_ha: float | None = None
    input_multiplier: float = 1.0
    extra_input_t_c_ha: float = 0.0
    manure_t_c_ha: float = 0.0
    input_months: tuple[float, ...] = EVEN
    covered: tuple[bool, ...] = tuple([True] * 12)
    flooded: tuple[bool, ...] = tuple([False] * 12)
    dpm_rpm: float = DPM_RPM["crop"]
    practices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.input_months) != 12 or len(self.covered) != 12 or len(self.flooded) != 12:
            raise ValueError("monthly profiles need twelve entries")
        if abs(sum(self.input_months) - 1.0) > 1e-6:
            raise ValueError("input_months must sum to 1")
        if self.dpm_rpm <= 0:
            raise ValueError("DPM/RPM ratio must be positive")

    def annual_plant_input(self, baseline_input: float) -> float:
        base = self.plant_input_t_c_ha if self.plant_input_t_c_ha is not None else baseline_input
        return base * self.input_multiplier + self.extra_input_t_c_ha


@dataclass(frozen=True)
class Practice:
    """A practice change as RothC can represent it, or cannot.

    Effects are placeholders from meta-analytic ranges until a local trial
    replaces them; `rothc_can_see` is False where the mechanism is outside
    the model and the effect must not be credited from it.
    """

    id: str
    label: str
    input_multiplier: float = 1.0
    extra_input_t_c_ha: float = 0.0
    manure_t_c_ha: float = 0.0
    adds_cover_months: tuple[int, ...] = ()
    rothc_can_see: bool = True
    note: str = ""


PRACTICES: dict[str, Practice] = {p.id: p for p in (
    Practice("residue_retention", "Crop residue retained, not burned",
             input_multiplier=1.35,
             note="placeholder: +35% returned plant carbon where residue was "
                  "removed or burned; replace with measured residue biomass"),
    Practice("cover_crop", "Off-season cover crop",
             extra_input_t_c_ha=0.9,
             note="placeholder: 0.9 t C/ha/yr above- and below-ground; "
                  "cover is added in the named fallow months"),
    Practice("manure", "Farmyard manure / compost",
             manure_t_c_ha=1.2,
             note="placeholder: 1.2 t C/ha/yr; imported manure is a "
                  "leakage question under VM0042, not free carbon"),
    Practice("agroforestry_litter", "Tree litter on cropland",
             extra_input_t_c_ha=0.6,
             note="placeholder: litter only; tree biomass is credited under VM0047"),
    Practice("reduced_tillage", "Reduced or zero tillage",
             rothc_can_see=False,
             note="RothC has no tillage term; any gain here would be invented"),
)}


def apply_practices(baseline: Management, practice_ids: list[str],
                    *, fallow_months: tuple[int, ...] = ()) -> tuple[Management, list[str]]:
    """The project management: the baseline plus practices. Returns warnings."""
    warnings: list[str] = []
    m = replace(baseline, name="project")
    covered = list(baseline.covered)
    for pid in practice_ids:
        p = PRACTICES.get(pid)
        if p is None:
            raise ValueError(f"unknown practice {pid!r}; known: {sorted(PRACTICES)}")
        if not p.rothc_can_see:
            warnings.append(f"{p.label}: {p.note}. It contributes nothing to this projection.")
            continue
        m = replace(m, input_multiplier=m.input_multiplier * p.input_multiplier,
                    extra_input_t_c_ha=m.extra_input_t_c_ha + p.extra_input_t_c_ha,
                    manure_t_c_ha=m.manure_t_c_ha + p.manure_t_c_ha)
        if pid == "cover_crop":
            for mo in fallow_months or p.adds_cover_months:
                covered[mo - 1] = True
        if pid == "manure":
            warnings.append("manure: carbon moved from elsewhere is not "
                            "sequestration unless its counterfactual fate is "
                            "accounted; VM0042 treats this as leakage")
    m = replace(m, covered=tuple(covered), practices=tuple(practice_ids))
    return m, warnings


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------

@dataclass
class Pools:
    dpm: float = 0.0
    rpm: float = 0.0
    bio: float = 0.0
    hum: float = 0.0
    iom: float = 0.0

    @property
    def active(self) -> float:
        return self.dpm + self.rpm + self.bio + self.hum

    @property
    def total(self) -> float:
        return self.active + self.iom

    def vector(self) -> list[float]:
        return [self.dpm, self.rpm, self.bio, self.hum]

    @classmethod
    def from_vector(cls, v: list[float], iom: float) -> "Pools":
        return cls(v[0], v[1], v[2], v[3], iom)


@dataclass
class RothC:
    clay_pct: float
    depth_cm: float = 23.0

    def __post_init__(self) -> None:
        if not 0 <= self.clay_pct <= 100:
            raise ValueError("clay must be a percentage")

    def step(self, p: Pools, w: MonthlyWeather, *, covered: bool, flooded: bool,
             acc_tsmd: float, plant_c: float, fym_c: float,
             dpm_rpm: float) -> tuple[Pools, float, float]:
        """Advance one month. Returns (pools, new accumulated deficit, CO2-C)."""
        # Moisture deficit: rain minus evaporation, where RothC's 0.75 x open
        # pan is taken as the reference ET the connectors supply.
        max_def = max_tsmd(self.clay_pct, self.depth_cm, bare=not covered)
        balance = w.rain_mm - w.pet_mm
        if balance < 0 or acc_tsmd < 0:
            acc_tsmd = min(0.0, max(max_def, acc_tsmd + balance))
        a = temperature_modifier(w.temp_c)
        b = 1.0 if flooded else moisture_modifier(acc_tsmd, max_tsmd(self.clay_pct, self.depth_cm))
        c = 0.6 if covered else 1.0
        rate = a * b * c * (PADDY_RATE_FACTOR if flooded else 1.0) / 12.0

        def lost(pool: float, k: float) -> float:
            return pool * (1.0 - math.exp(-rate * k))

        d_dpm, d_rpm = lost(p.dpm, K_DPM), lost(p.rpm, K_RPM)
        d_bio, d_hum = lost(p.bio, K_BIO), lost(p.hum, K_HUM)
        decomposed = d_dpm + d_rpm + d_bio + d_hum
        f_co2 = co2_fraction(self.clay_pct)
        kept = decomposed * (1.0 - f_co2)

        dpm_frac = dpm_rpm / (1.0 + dpm_rpm)
        new = Pools(
            dpm=p.dpm - d_dpm + plant_c * dpm_frac + fym_c * FYM_SPLIT[0],
            rpm=p.rpm - d_rpm + plant_c * (1 - dpm_frac) + fym_c * FYM_SPLIT[1],
            bio=p.bio - d_bio + kept * BIO_SHARE,
            hum=p.hum - d_hum + kept * (1 - BIO_SHARE) + fym_c * FYM_SPLIT[2],
            iom=p.iom,
        )
        return new, acc_tsmd, decomposed * f_co2

    def run_year(self, p: Pools, months: list[MonthlyWeather], m: Management,
                 plant_input: float, acc: float = 0.0) -> tuple[Pools, float]:
        for i, w in enumerate(months):
            p, acc, _ = self.step(
                p, w, covered=m.covered[i], flooded=m.flooded[i], acc_tsmd=acc,
                plant_c=plant_input * m.input_months[i],
                fym_c=m.manure_t_c_ha * m.input_months[i], dpm_rpm=m.dpm_rpm)
        return p, acc

    def equilibrium(self, normals: list[MonthlyWeather], m: Management,
                    plant_input: float, iom: float) -> Pools:
        """The steady state, solved exactly rather than spun up.

        One year of RothC is an affine map on the four active pools,
        x' = A x + b, because every pool decays first-order at rates that do
        not depend on the pools. So the steady state is (I - A)^-1 b, and
        A's columns are one year applied to each unit pool with no input.
        The moisture deficit is carried through the year from zero, the
        same way in every column, so it does not break linearity.
        """
        zero = replace(m, manure_t_c_ha=0.0)
        cols = []
        for k in range(4):
            v = [0.0] * 4
            v[k] = 1.0
            out, _ = self.run_year(Pools.from_vector(v, 0.0), normals, zero, 0.0)
            cols.append(out.vector())
        a = [[cols[j][i] for j in range(4)] for i in range(4)]
        b_pools, _ = self.run_year(Pools(iom=0.0), normals, m, plant_input)
        b = b_pools.vector()
        lhs = [[(1.0 if i == j else 0.0) - a[i][j] for j in range(4)] for i in range(4)]
        return Pools.from_vector(_solve(lhs, b), iom)

    def solve_input(self, normals: list[MonthlyWeather], m: Management,
                    target_soc_t_ha: float) -> tuple[float, Pools]:
        """Plant input that holds `target_soc` at equilibrium, and the pools.

        Equilibrium active carbon is linear in plant input (with manure held
        fixed), so one unit run and one zero run pin the line exactly.
        """
        iom = falloon_iom(target_soc_t_ha)
        at_zero = self.equilibrium(normals, m, 0.0, iom).active
        at_one = self.equilibrium(normals, m, 1.0, iom).active
        slope = at_one - at_zero
        need = target_soc_t_ha - iom - at_zero
        if slope <= 0 or need <= 0:
            raise ValueError(
                f"cannot hold {target_soc_t_ha:.1f} t C/ha at equilibrium under "
                f"{m.name}: manure alone already exceeds it, or the climate "
                f"decomposes everything")
        plant = need / slope
        return plant, self.equilibrium(normals, m, plant, iom)

    def project(self, start: Pools, months_by_year: list[list[MonthlyWeather]],
                m: Management, plant_input: float) -> list[float]:
        """Total SOC at the end of each year."""
        out = []
        p, acc = start, 0.0
        for months in months_by_year:
            p, acc = self.run_year(p, months, m, plant_input, acc)
            out.append(p.total)
        return out


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting. Four unknowns."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-15:
            raise ValueError("steady state is singular")
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col:
                f = m[r][col] / m[col][col]
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


# ---------------------------------------------------------------------------
# Projection with uncertainty
# ---------------------------------------------------------------------------

@dataclass
class SocProjection:
    """Baseline against project, with the spread that inputs alone produce."""

    years: list[int]
    baseline_t_c_ha: list[float]
    project_t_c_ha: list[float]
    delta_p05: list[float]
    delta_p95: list[float]
    plant_input_t_c_ha: float
    initial_soc_t_c_ha: float
    clay_pct: float
    climate_source: str
    is_climatology: bool
    warnings: list[str] = field(default_factory=list)
    calculation: Calculation | None = None

    @property
    def delta_t_c_ha(self) -> list[float]:
        return [p - b for p, b in zip(self.project_t_c_ha, self.baseline_t_c_ha)]

    @property
    def horizon(self) -> int:
        return len(self.years)

    def annual_t_co2e_ha(self) -> float:
        """Mean annual removal over the horizon, tCO2e/ha/yr."""
        return self.delta_t_c_ha[-1] * CARBON_TO_CO2E / self.horizon

    def relative_uncertainty(self) -> float:
        """Half-width of the 90% interval on the final change, over the mean."""
        mean = self.delta_t_c_ha[-1]
        if mean <= 0:
            return 1.0
        return (self.delta_p95[-1] - self.delta_p05[-1]) / 2.0 / mean

    def ex_ante_t_co2e_ha_yr(self) -> float:
        """What a project description could state: the mean less the
        uncertainty deduction the same standard applies at verification."""
        ded = uncertainty_deduction(self.relative_uncertainty())
        return max(0.0, self.annual_t_co2e_ha() * (1 - ded.fraction))

    def to_dict(self) -> dict:
        return {
            "years": self.years,
            "baseline_t_c_ha": [round(v, 3) for v in self.baseline_t_c_ha],
            "project_t_c_ha": [round(v, 3) for v in self.project_t_c_ha],
            "delta_t_c_ha": [round(v, 3) for v in self.delta_t_c_ha],
            "delta_p05": [round(v, 3) for v in self.delta_p05],
            "delta_p95": [round(v, 3) for v in self.delta_p95],
            "plant_input_t_c_ha": round(self.plant_input_t_c_ha, 3),
            "initial_soc_t_c_ha": round(self.initial_soc_t_c_ha, 2),
            "clay_pct": round(self.clay_pct, 1),
            "climate_source": self.climate_source,
            "is_climatology": self.is_climatology,
            "annual_t_co2e_ha": round(self.annual_t_co2e_ha(), 4),
            "relative_uncertainty": round(self.relative_uncertainty(), 4),
            "ex_ante_t_co2e_ha_yr": round(self.ex_ante_t_co2e_ha_yr(), 4),
            "warnings": self.warnings,
            "calculation": self.calculation.to_dict() if self.calculation else None,
        }


def _quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def project_soc(climate: ClimateSeries, *, clay_pct: float, initial_soc_t_c_ha: float,
                baseline: Management, practices: list[str], start_year: int,
                horizon: int = 20, fallow_months: tuple[int, ...] = (),
                clay_sigma: float = 3.0, soc_sigma_frac: float = 0.10,
                effect_sigma_frac: float = 0.30, draws: int = 200,
                seed: int = 7) -> SocProjection:
    """Project baseline and project SOC, and the spread of the difference.

    The central run uses the stated inputs. The interval comes from redrawing
    the three inputs nobody knows well -- clay, the initial stock, and the
    size of the practice effect -- and re-solving the equilibrium each time,
    because a different starting stock implies a different baseline input.
    Seeded, so the interval in a project description can be rebuilt.
    """
    normals = climate.normals() if not climate.is_climatology else list(climate.months)
    years = list(range(start_year, start_year + horizon))
    weather = [normals] * horizon
    project, warnings = apply_practices(baseline, practices, fallow_months=fallow_months)
    if not climate.is_climatology:
        warnings.append("projection repeats the retrieved period's mean year; "
                        "a hindcast would use the months themselves")
    if any(baseline.flooded):
        warnings.append("paddy months use the Shirato & Yokozawa (2005) flooded-rate "
                        "factor; unmodified RothC over-predicts decomposition in paddy")

    def one(clay: float, soc0: float, effect: float) -> tuple[list[float], list[float], float]:
        model = RothC(clay)
        plant, pools = model.solve_input(normals, baseline, soc0)
        scaled = replace(
            project,
            input_multiplier=1.0 + (project.input_multiplier - 1.0) * effect,
            extra_input_t_c_ha=project.extra_input_t_c_ha * effect,
            manure_t_c_ha=baseline.manure_t_c_ha
            + (project.manure_t_c_ha - baseline.manure_t_c_ha) * effect)
        base_series = model.project(pools, weather, baseline,
                                    baseline.annual_plant_input(plant))
        proj_series = model.project(pools, weather, scaled,
                                    scaled.annual_plant_input(plant))
        return base_series, proj_series, plant

    base, proj, plant = one(clay_pct, initial_soc_t_c_ha, 1.0)

    rng = random.Random(seed)
    deltas: list[list[float]] = []
    for _ in range(draws):
        clay = min(80.0, max(1.0, rng.gauss(clay_pct, clay_sigma)))
        soc0 = max(5.0, rng.gauss(initial_soc_t_c_ha, initial_soc_t_c_ha * soc_sigma_frac))
        effect = max(0.0, rng.gauss(1.0, effect_sigma_frac))
        b, p, _ = one(clay, soc0, effect)
        deltas.append([pv - bv for pv, bv in zip(p, b)])
    p05 = [_quantile([d[i] for d in deltas], 0.05) for i in range(horizon)]
    p95 = [_quantile([d[i] for d in deltas], 0.95) for i in range(horizon)]

    result = SocProjection(years, base, proj, p05, p95, plant, initial_soc_t_c_ha,
                           clay_pct, climate.source, climate.is_climatology, warnings)

    calc = Calculation("RothC-26.3 ex-ante SOC projection", "tCO2e/ha/yr")
    calc.cite("Coleman & Jenkinson (1996, rev. 2014), RothC-26.3 model description")
    calc.cite("Falloon et al. (1998), inert organic matter from total SOC")
    calc.cite("Verra VM0042 v2.x measure-and-model approach; VMD0053 for validation")
    calc.add("clay", clay_pct, "%")
    calc.add("initial SOC (0-30 cm)", initial_soc_t_c_ha, "t C/ha")
    calc.add("inert organic matter", falloon_iom(initial_soc_t_c_ha), "t C/ha",
             "0.049 x SOC^1.139")
    calc.add("baseline plant input, solved", plant, "t C/ha/yr",
             "steady-state assumption: baseline held the soil at equilibrium")
    calc.add("project plant input", project.annual_plant_input(plant), "t C/ha/yr",
             ", ".join(practices) or "no practice change")
    if project.manure_t_c_ha:
        calc.add("manure input", project.manure_t_c_ha, "t C/ha/yr")
    calc.add(f"SOC change after {horizon} years", result.delta_t_c_ha[-1], "t C/ha",
             f"90% interval {p05[-1]:.2f} to {p95[-1]:.2f} over {draws} seeded draws")
    calc.add("mean annual removal", result.annual_t_co2e_ha(), "tCO2e/ha/yr")
    ded = uncertainty_deduction(result.relative_uncertainty())
    calc.add("uncertainty deduction", ded.fraction, "fraction", ded.basis)
    calc.finish(result.ex_ante_t_co2e_ha_yr())
    result.calculation = calc
    return result
