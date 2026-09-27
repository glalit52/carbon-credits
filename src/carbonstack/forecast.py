"""Forward delivery: how many credits will actually arrive, and when.

Everything else in this package answers "how many credits does this vintage
carry". That is a backward-looking question about evidence already gathered.
A project developer has to answer a forward-looking one, and it is the
question the business actually turns on: **how much can we sell forward
without having to buy our way out of it?**

Those are not the same number. A vintage's `net_t` is a point estimate with
an uncertainty deduction already taken. A forward commitment is a promise
against a future the project does not control, and the ways it goes wrong
are not measurement error:

  * A farmer leaves. Contracts lapse, land changes hands, someone takes a
    better offer. The hectares simply stop being enrolled.
  * A season lapses. The practice is not followed, and the product now
    *detects* that rather than assuming it away -- 2026 Kuruvai scored 25%.
  * A planting fails. Drought, fire, grazing; survival drops under the floor
    and the plot is excluded from the vintage rather than credited down.
  * Verification slips. The commonest cause of a missed offtake is not that
    the carbon was not there, it is that the paperwork arrived in March
    rather than December. This is a timing risk, not a volume risk, and
    modelling it as volume hides it.

Selling the point estimate forward is the mistake this module exists to
prevent. If a developer pre-sells P50 they miss half the time, and covering
a shortfall means buying replacement credits at spot, into a market that is
tight precisely when everyone's projects underdelivered for the same reason.
So the headline output is not the expected delivery. It is
`safe_forward_volume` -- the level the project clears with the stated
confidence -- and the expected cost of the tail beyond it.

The simulation is seeded and reproducible. That matters here more than
statistical elegance: a number in a term sheet must be rebuildable months
later, by someone else, from the committed inputs.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .audit import Calculation

#: Trials. Enough that the P90 is stable to about a tenth of a tonne on a
#: portfolio of any size, cheap enough to run inside a build.
DEFAULT_TRIALS = 4000

#: Default confidence for a forward sale. Not a convention -- a choice. At
#: 90% a developer misses one commitment in ten, which is survivable if the
#: shortfall cost is budgeted; at 50% they miss half and are not a
#: counterparty anyone signs twice.
DEFAULT_CONFIDENCE = 0.90


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VintageProjection:
    """One future vintage as the engine currently projects it."""

    year: int
    net_t: float
    relative_uncertainty: float
    #: "rice" | "agroforestry" | "cropland". Decides which risks apply: a
    #: planting can fail, a methane claim cannot.
    track: str = "agroforestry"
    #: True once the year has closed and the evidence is in. A settled
    #: vintage carries measurement uncertainty but no delivery risk.
    settled: bool = False


@dataclass(frozen=True)
class RiskModel:
    """The ways a projected credit fails to arrive.

    Every rate here is a placeholder and marked as one. They are the inputs
    a developer should argue about with their own portfolio data, which is
    why they are parameters rather than constants buried in the arithmetic.
    """

    #: Annual probability that an enrolled farmer leaves the programme.
    #: Smallholder aggregation projects report wide ranges; 8% is a
    #: mid-range placeholder and compounds, which is the point -- over a
    #: ten-year crediting period it is most of the portfolio.
    dropout_per_year: float = 0.08

    #: Probability that a season's practice is not followed. The rice
    #: pathway now detects this directly, so the prior can be checked
    #: against what the radar found rather than asserted forever.
    practice_lapse_per_year: float = 0.12

    #: Probability that a planting fails badly enough in a given year to
    #: fall below the survival floor and be excluded from the vintage.
    planting_failure_per_year: float = 0.05

    #: Probability that a vintage's verification slips past the delivery
    #: window. Slipped credits are not lost -- they arrive in the next
    #: year -- so this moves volume through time rather than destroying it.
    verification_slip_per_year: float = 0.18

    #: Multiplier on the engine's relative uncertainty when treating it as
    #: the standard deviation of a delivery distribution. The engine's
    #: figure is a measurement error; realised delivery is at least that
    #: uncertain and usually more, because the measurement is of a system
    #: that is itself variable.
    measurement_sigma_scale: float = 1.0

    #: How many independently-failing units the portfolio is. A single-plot
    #: pilot is one: the farmer leaves or does not, and there is no
    #: averaging to hide behind. A thousand-farmer programme is a thousand,
    #: and the law of large numbers does most of the risk management. This
    #: is the parameter that decides whether the forecast has a fat tail,
    #: and it is a property of the portfolio, not of the world -- which is
    #: why aggregation is a risk control and not just an admin cost.
    enrolled_units: int = 1

    source: str = ("placeholder rates -- replace with the portfolio's own "
                   "attrition, lapse and verification history")

    def applies_to(self, track: str) -> tuple[bool, bool]:
        """(practice lapse applies, planting failure applies)."""
        return (track in ("rice", "cropland"), track == "agroforestry")


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated quantile. `q` is a fraction in [0, 1]."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return sorted_values[int(pos)]
    return (sorted_values[low] * (high - pos)
            + sorted_values[high] * (pos - low))


@dataclass
class YearForecast:
    """The delivery distribution for one vintage year."""

    year: int
    projected_t: float
    p10: float
    p50: float
    p90: float
    mean: float
    #: The volume this year clears with the stated confidence. This is the
    #: number that may be sold forward.
    safe_t: float
    confidence: float
    #: How often the simulation delivered nothing at all for this year.
    zero_rate: float

    @property
    def haircut(self) -> float:
        """How much of the projection is not safe to sell."""
        if self.projected_t <= 0:
            return 0.0
        return 1 - self.safe_t / self.projected_t

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "projected_t": round(self.projected_t, 3),
            "p10": round(self.p10, 3),
            "p50": round(self.p50, 3),
            "p90": round(self.p90, 3),
            "mean": round(self.mean, 3),
            "safe_t": round(self.safe_t, 3),
            "confidence": self.confidence,
            "haircut": round(self.haircut, 4),
            "zero_rate": round(self.zero_rate, 4),
        }


@dataclass
class Forecast:
    """A portfolio's forward delivery, and what may be promised against it."""

    project_id: str
    trials: int
    confidence: float
    years: list[YearForecast] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    risk_source: str = ""

    #: Totals over the forecast horizon.
    projected_total_t: float = 0.0
    p50_total_t: float = 0.0
    safe_total_t: float = 0.0

    #: One-at-a-time sensitivity: {risk name: safe volume with that risk off}.
    sensitivity: dict[str, float] = field(default_factory=dict)

    @property
    def portfolio_haircut(self) -> float:
        if self.projected_total_t <= 0:
            return 0.0
        return 1 - self.safe_total_t / self.projected_total_t

    @property
    def dominant_risk(self) -> tuple[str, float] | None:
        """Which risk costs the most safe volume, and how much.

        A developer with one thing to fix should be told which one. The
        answer is usually not the one the methodology worries about.
        """
        if not self.sensitivity:
            return None
        name, without = max(self.sensitivity.items(),
                            key=lambda kv: kv[1] - self.safe_total_t)
        return name, without - self.safe_total_t

    def report(self) -> Calculation:
        c = Calculation(f"forward delivery, {self.project_id}", "tCO2e")
        c.cite(f"{self.trials:,} simulated portfolios, seeded and reproducible")
        c.cite(self.risk_source)
        c.add("projected delivery", self.projected_total_t, "tCO2e",
              "the engine's point estimate, summed over the horizon")
        c.add("median delivery", self.p50_total_t, "tCO2e")
        c.add("confidence", self.confidence, "fraction",
              "the level a forward commitment must clear")
        c.add("portfolio haircut", self.portfolio_haircut, "fraction",
              "how much of the projection is not safe to promise")
        dominant = self.dominant_risk
        if dominant:
            c.add(f"cost of {dominant[0]}", dominant[1], "tCO2e",
                  "safe volume recovered if this risk were eliminated")
        c.finish(self.safe_total_t)
        return c

    def to_dict(self) -> dict:
        dominant = self.dominant_risk
        return {
            "project_id": self.project_id,
            "trials": self.trials,
            "confidence": self.confidence,
            "projected_total_t": round(self.projected_total_t, 3),
            "p50_total_t": round(self.p50_total_t, 3),
            "safe_total_t": round(self.safe_total_t, 3),
            "portfolio_haircut": round(self.portfolio_haircut, 4),
            "years": [y.to_dict() for y in self.years],
            "sensitivity": {k: round(v, 3) for k, v in self.sensitivity.items()},
            "dominant_risk": ({"risk": dominant[0],
                               "safe_volume_cost_t": round(dominant[1], 3)}
                              if dominant else None),
            "warnings": list(self.warnings),
            "risk_source": self.risk_source,
        }


@dataclass
class OfftakeAssessment:
    """Can this project sign that contract?"""

    committed_t: float
    delivery_probability: float
    expected_shortfall_t: float
    worst_case_shortfall_t: float
    replacement_price: float
    expected_cover_cost: float
    verdict: str

    def to_dict(self) -> dict:
        return {
            "committed_t": round(self.committed_t, 3),
            "delivery_probability": round(self.delivery_probability, 4),
            "expected_shortfall_t": round(self.expected_shortfall_t, 3),
            "worst_case_shortfall_t": round(self.worst_case_shortfall_t, 3),
            "replacement_price": self.replacement_price,
            "expected_cover_cost": round(self.expected_cover_cost, 2),
            "verdict": self.verdict,
        }


# ---------------------------------------------------------------------------
# The simulation
# ---------------------------------------------------------------------------

def _simulate(projections: list[VintageProjection], risk: RiskModel,
              trials: int, seed: int,
              disable: str | None = None) -> dict[int, list[float]]:
    """Run the portfolio `trials` times. Returns delivered tonnes by year.

    `disable` switches one risk off, which is how the sensitivity is built:
    the cost of a risk is what the forecast would be worth without it.
    """
    rng = random.Random(seed)
    years = sorted({p.year for p in projections})
    draws: dict[int, list[float]] = {y: [] for y in years}

    dropout = 0.0 if disable == "farmer dropout" else risk.dropout_per_year
    lapse = 0.0 if disable == "practice lapse" else risk.practice_lapse_per_year
    failure = (0.0 if disable == "planting failure"
               else risk.planting_failure_per_year)
    slip = (0.0 if disable == "verification slip"
            else risk.verification_slip_per_year)
    sigma_scale = (0.0 if disable == "measurement uncertainty"
                   else risk.measurement_sigma_scale)

    first_year = years[0] if years else 0

    units = max(1, risk.enrolled_units)

    def survivors(alive: int, hazard: float) -> int:
        """How many of `alive` units come through one year.

        Drawn, not averaged. On a one-farmer pilot this is a coin flip and
        the forecast inherits a cliff; across a thousand farmers it
        concentrates and the cliff becomes a wobble. That difference is the
        whole case for aggregation, and averaging it away here would hide
        the risk the developer is actually carrying.
        """
        if hazard <= 0 or alive <= 0:
            return alive
        if alive > 400:
            # Normal approximation, so a large programme stays cheap to run.
            mean = alive * (1 - hazard)
            sd = math.sqrt(alive * hazard * (1 - hazard))
            return max(0, min(alive, round(rng.gauss(mean, sd))))
        return sum(1 for _ in range(alive) if rng.random() >= hazard)

    for _ in range(trials):
        delivered = {y: 0.0 for y in years}
        # Dropout is a survival process across the whole horizon, not an
        # independent coin flip per year: once a farmer has left, they are
        # gone for every later vintage. Modelling it per-year independently
        # is the single easiest way to under-state attrition.
        alive = units
        carried = 0.0          # volume slipped out of the previous year
        last_year = years[-1] if years else 0

        for p in projections:
            if p.settled:
                # Already verified. Measurement uncertainty still applies to
                # what a registry finally issues, but nothing else does.
                volume = p.net_t
                if sigma_scale > 0 and p.relative_uncertainty > 0:
                    volume *= max(0.0, rng.gauss(
                        1.0, p.relative_uncertainty * sigma_scale))
                delivered[p.year] += volume
                continue

            if p.year > first_year:
                alive = survivors(alive, dropout)
            volume = p.net_t * (alive / units)

            practice_risk, planting_risk = risk.applies_to(p.track)
            if practice_risk and alive:
                # A lapsed season is not a reduced season on the units it
                # hits: the abatement did not happen and the detector finds
                # nothing to credit. Other farmers still delivered.
                volume *= survivors(alive, lapse) / alive
            if planting_risk and alive:
                volume *= survivors(alive, failure) / alive

            if volume > 0 and sigma_scale > 0 and p.relative_uncertainty > 0:
                volume *= max(0.0, rng.gauss(
                    1.0, p.relative_uncertainty * sigma_scale))

            volume += carried
            carried = 0.0

            # Verification is a programme-level event: one auditor, one
            # registry queue, one report. It slips for everybody or nobody,
            # which is why aggregation does not diversify it away.
            if rng.random() < slip and p.year != last_year:
                # Slipped, not lost -- it lands in the following year. On
                # the last year of the horizon there is no following year
                # inside the window, so a slip there is a miss, which is
                # exactly the risk a year-end offtake carries.
                carried = volume
                volume = 0.0
            elif rng.random() < slip and p.year == last_year:
                volume = 0.0

            delivered[p.year] += volume

        for y in years:
            draws[y].append(delivered[y])
    return draws


def run(projections: list[VintageProjection], *,
        project_id: str = "portfolio",
        risk: RiskModel | None = None,
        trials: int = DEFAULT_TRIALS,
        confidence: float = DEFAULT_CONFIDENCE,
        seed: int = 20260927,
        sensitivity: bool = True) -> Forecast:
    """Forecast forward delivery and the volume it is safe to promise."""
    risk = risk or RiskModel()
    if not 0.5 <= confidence < 1.0:
        raise ValueError(
            "confidence must be in [0.5, 1.0): below a coin flip is not a "
            "commitment, and certainty is not available")
    projections = sorted(projections, key=lambda p: p.year)

    forecast = Forecast(project_id=project_id, trials=trials,
                        confidence=confidence, risk_source=risk.source)
    if not projections:
        forecast.warnings.append(
            "nothing to forecast: no projected vintages were supplied")
        return forecast

    draws = _simulate(projections, risk, trials, seed)
    totals = sorted(sum(draws[y][i] for y in draws) for i in range(trials))

    for p in projections:
        if any(y.year == p.year for y in forecast.years):
            continue
        values = sorted(draws[p.year])
        same_year = [q.net_t for q in projections if q.year == p.year]
        forecast.years.append(YearForecast(
            year=p.year,
            projected_t=sum(same_year),
            p10=_quantile(values, 0.10),
            p50=_quantile(values, 0.50),
            p90=_quantile(values, 0.90),
            mean=sum(values) / len(values),
            # The safe level is the LOWER tail: the volume exceeded in
            # `confidence` of futures. Reading the upper quantile here is
            # the error that sells a project into a shortfall.
            safe_t=_quantile(values, 1 - confidence),
            confidence=confidence,
            zero_rate=sum(1 for v in values if v <= 0) / len(values),
        ))

    forecast.projected_total_t = sum(p.net_t for p in projections)
    forecast.p50_total_t = _quantile(totals, 0.50)
    forecast.safe_total_t = _quantile(totals, 1 - confidence)

    if sensitivity:
        for name in ("farmer dropout", "practice lapse", "planting failure",
                     "verification slip", "measurement uncertainty"):
            alt = _simulate(projections, risk, trials, seed, disable=name)
            alt_totals = sorted(
                sum(alt[y][i] for y in alt) for i in range(trials))
            forecast.sensitivity[name] = _quantile(alt_totals, 1 - confidence)

    unsettled = [p for p in projections if not p.settled]
    if not unsettled:
        forecast.warnings.append(
            "every vintage supplied is already settled; this is a restatement "
            "of measurement uncertainty, not a forecast")
    if forecast.portfolio_haircut > 0.5:
        forecast.warnings.append(
            f"{forecast.portfolio_haircut:.0%} of the projected volume is "
            f"not safe to promise; a forward sale at the projection would be "
            f"a short position")
    unsellable = [y for y in forecast.years if y.safe_t <= 0 and y.projected_t > 0]
    if unsellable and forecast.safe_total_t > 0:
        forecast.warnings.append(
            f"{len(unsellable)} of {len(forecast.years)} vintages clear "
            f"nothing at {confidence:.0%} on their own, while the horizon as "
            f"a whole clears {forecast.safe_total_t:,.0f} t: sell the period "
            f"as a basket with a delivery window, not year by year. A "
            f"slipped verification is only a miss when the contract names a "
            f"single December")
    thin = [y for y in forecast.years if y.zero_rate > 0.25]
    if thin:
        forecast.warnings.append(
            f"{len(thin)} year(s) deliver nothing in more than a quarter of "
            f"futures: {', '.join(str(y.year) for y in thin)}")
    return forecast


def aggregation_curve(projections: list[VintageProjection], *,
                      units: tuple[int, ...] = (1, 5, 25, 100, 500, 2000),
                      risk: RiskModel | None = None,
                      trials: int = 1500,
                      confidence: float = DEFAULT_CONFIDENCE,
                      seed: int = 20260927) -> list[dict]:
    """How much the project could safely promise at each portfolio size.

    "How many farmers before we can sign an offtake" is the question a
    developer actually has to answer, and it has a numeric answer. The curve
    rises steeply and then flattens: past a few dozen units, attrition and
    crop failure have diversified away and what is left -- verification
    timing, measurement error -- is programme-level and does not care how
    many farmers there are. Where it flattens is where aggregation stops
    buying risk reduction and starts only buying volume.
    """
    base = risk or RiskModel()
    out = []
    previous = None
    for n in units:
        f = run(projections, risk=RiskModel(**{**base.__dict__,
                                               "enrolled_units": n}),
                trials=trials, confidence=confidence, seed=seed,
                sensitivity=False)
        row = {
            "units": n,
            "safe_t": round(f.safe_total_t, 3),
            "p50_t": round(f.p50_total_t, 3),
            "haircut": round(f.portfolio_haircut, 4),
            "gain_over_previous_t": (round(f.safe_total_t - previous, 3)
                                     if previous is not None else None),
        }
        previous = f.safe_total_t
        out.append(row)
    return out


def assess_offtake(forecast: Forecast, projections: list[VintageProjection],
                   *, committed_t: float, replacement_price: float,
                   risk: RiskModel | None = None,
                   seed: int = 20260927) -> OfftakeAssessment:
    """What a given forward commitment actually costs in expectation.

    A shortfall is not a missed sale, it is a purchase: the developer buys
    replacement credits at whatever spot is on the day, which is high
    precisely when their own project underdelivered, because the weather
    that hurt them hurt everyone nearby. `replacement_price` should be set
    well above the contracted price for that reason.
    """
    risk = risk or RiskModel()
    draws = _simulate(projections, risk, forecast.trials, seed)
    totals = [sum(draws[y][i] for y in draws) for i in range(forecast.trials)]

    shortfalls = [max(0.0, committed_t - t) for t in totals]
    met = sum(1 for s in shortfalls if s <= 0) / len(shortfalls)
    expected = sum(shortfalls) / len(shortfalls)
    worst = max(shortfalls)

    if met >= forecast.confidence:
        verdict = (f"signable: delivers in {met:.0%} of futures, at or above "
                   f"the {forecast.confidence:.0%} bar")
    elif met >= 0.5:
        verdict = (f"under-collateralised: delivers in only {met:.0%} of "
                   f"futures; budget the cover cost or cut the volume to "
                   f"{forecast.safe_total_t:,.0f} t")
    else:
        verdict = (f"do not sign: delivers in {met:.0%} of futures, so the "
                   f"likely outcome is buying {expected:,.0f} t on the spot "
                   f"market")

    return OfftakeAssessment(
        committed_t=committed_t,
        delivery_probability=met,
        expected_shortfall_t=expected,
        worst_case_shortfall_t=worst,
        replacement_price=replacement_price,
        expected_cover_cost=expected * replacement_price,
        verdict=verdict,
    )


def from_vintages(vintages, *, track: str,
                  settled_through: int | None = None
                  ) -> list[VintageProjection]:
    """Adapt stored or projected vintages into forecast inputs."""
    out = []
    for v in vintages:
        year = v["year"] if isinstance(v, dict) else v.year
        net = v["net_t"] if isinstance(v, dict) else v.net_t
        unc = (v.get("relative_uncertainty", 0.0) if isinstance(v, dict)
               else v.relative_uncertainty)
        if isinstance(v, dict) and "complete" in v:
            settled = bool(v["complete"])
        else:
            settled = (settled_through is not None and year <= settled_through)
        out.append(VintageProjection(year=year, net_t=net,
                                     relative_uncertainty=unc,
                                     track=track, settled=settled))
    return out
