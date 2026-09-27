"""Sentinel-1 SAR: was the field actually dry?

The rice pathway credits avoided methane, and methane is avoided when the
paddy is not flooded. So the entire claim rests on one observable -- the
water state of the field, several times per season, for every plot -- and
until now the product asserted it. The feed knew whether a dry-down had
happened and handed that straight to the confidence term. Nothing detected
anything.

Two reasons it has to be SAR rather than optical:

**Cloud.** AWD is practised in the monsoon. Tamil Nadu's Samba season runs
through the north-east monsoon, and an optical sensor loses most of its
passes to cloud exactly when the evidence matters. C-band radar does not
care about cloud, and Sentinel-1 gives a 6-day revisit with both satellites.

**Water is what radar is good at.** A flooded field is a mirror: it
scatters the pulse away from the sensor and comes back dark. That is the
cleanest signal in the whole product.

It is also the trap. A *bare* flooded field is dark, but a flooded field
with a rice canopy is **bright** -- the stems and the water surface form a
dihedral and the pulse comes back twice (double bounce). So VV backscatter
over flooded paddy starts around -19 dB at transplanting and climbs past a
drained field's response by mid-season. A fixed threshold, which is how most
published flood maps work, is right in June and inverted in September.

`WaterRegimeDetector` handles that by estimating crop stage from VH (which
tracks canopy volume and is largely indifferent to what is underneath), then
comparing VV against what each state would produce *at that stage*. Where the
two states are separated by less than the noise -- which physically happens,
around the crossover -- it returns AMBIGUOUS rather than a coin flip.

Nothing here sees the true water state. The simulator produces backscatter
and the detector reads backscatter, which is the only arrangement in which
the detection numbers mean anything. `score()` exists so the tests can say
what it actually recovered.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from .audit import Calculation

S1_REVISIT_DAYS = 6
"""Sentinel-1 A+B at these latitudes. One satellite alone gives 12, which
halves the evidence for the same season and is worth stating in a project
document rather than discovering at verification."""

REFERENCE_INCIDENCE_DEG = 38.0
"""IW mid-swath. Backscatter falls with incidence angle, so passes from
different relative orbits are not comparable until they are normalised to
one reference."""

INCIDENCE_SLOPE_DB_PER_DEG = 0.10
"""Empirical cosine-law approximation over the IW swath. Small per degree,
and a swath spans 29-46 degrees, so ignoring it is worth up to 1.7 dB --
more than the separation between the two states near the crossover."""

SPECKLE_SIGMA_DB = 0.5
"""One standard deviation after averaging a field-sized parcel. A 2.5 ha plot
holds a few hundred 10 m pixels, so the equivalent number of looks is high
and the residual is a few tenths of a dB. A single looks-1 pixel is several
dB noisier, which is why parcel-level averaging is not an optimisation here
but the thing that makes the measurement possible at all."""

MIN_SEPARATION_DB = 1.2
"""Below this the two states are not distinguishable at this stage, and the
detector says so instead of guessing."""


class WaterState(Enum):
    FLOODED = "flooded"
    DRAINED = "drained"
    AMBIGUOUS = "ambiguous"


# ---------------------------------------------------------------------------
# The observation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SarPass:
    """One Sentinel-1 acquisition over one plot, as a pipeline receives it.

    Backscatter and geometry. No water state, no crop stage, no truth: what
    the detector is allowed to know is exactly what a granule carries.
    """

    day: date
    vv_db: float
    vh_db: float
    incidence_deg: float = REFERENCE_INCIDENCE_DEG
    relative_orbit: int = 63
    orbit_pass: str = "DESC"

    @property
    def vv_normalised_db(self) -> float:
        """VV corrected to the reference incidence angle."""
        return self.vv_db - INCIDENCE_SLOPE_DB_PER_DEG * (
            self.incidence_deg - REFERENCE_INCIDENCE_DEG)

    @property
    def vh_normalised_db(self) -> float:
        return self.vh_db - INCIDENCE_SLOPE_DB_PER_DEG * (
            self.incidence_deg - REFERENCE_INCIDENCE_DEG)

    @property
    def cross_ratio_db(self) -> float:
        """VH - VV. Rises as the canopy fills in."""
        return self.vh_normalised_db - self.vv_normalised_db

    def to_dict(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "vv_db": round(self.vv_db, 2),
            "vh_db": round(self.vh_db, 2),
            "incidence_deg": round(self.incidence_deg, 1),
            "relative_orbit": self.relative_orbit,
            "orbit_pass": self.orbit_pass,
        }


# ---------------------------------------------------------------------------
# The forward model -- used by the simulator, never by the detector
# ---------------------------------------------------------------------------

def _speckle(key: str, d: date, band: str) -> float:
    """Deterministic pseudo-noise in [-1, 1]. Reproducible builds matter more
    here than statistical purity."""
    h = hashlib.sha256(f"{key}|{d.isoformat()}|{band}".encode()).digest()
    return (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) * 2 - 1


def flooded_vv_db(stage: float) -> float:
    """Expected VV over a flooded paddy at a given canopy stage.

    Starts as a mirror and becomes a dihedral. The rise is the whole reason
    a fixed threshold fails.
    """
    return -19.0 + 13.0 * max(0.0, min(1.0, stage))


def drained_vv_db(stage: float) -> float:
    """Expected VV over a drained paddy. Rough soil scatters more than water,
    and the canopy adds a little volume on top."""
    return -12.5 + 1.0 * max(0.0, min(1.0, stage))


def expected_vh_db(stage: float) -> float:
    """VH is dominated by canopy volume, which is why it makes a usable stage
    proxy that the water state barely touches."""
    return -26.0 + 11.5 * max(0.0, min(1.0, stage))


CROSSOVER_STAGE = (12.5 - 19.0) / (1.0 - 13.0)
"""Where the two curves meet: stage 0.54. Before it a flooded field is
darker than a drained one; after it, brighter. Around it there is no
information in VV at all, and the detector says so rather than guessing."""


def simulate_pass(plot_key: str, day: date, *, water_frac: float,
                  stage: float, rain_mm: float = 0.0,
                  incidence_deg: float = REFERENCE_INCIDENCE_DEG,
                  relative_orbit: int = 63) -> SarPass:
    """Render a hidden water state as backscatter.

    Lives here beside the physics it inverts, but the detector must never
    call it. Wet soil after rain raises VV over a drained field, which is the
    confounder that produces most real false negatives.
    """
    w = max(0.0, min(1.0, water_frac))
    vv = (1 - w) * drained_vv_db(stage) + w * flooded_vv_db(stage)
    # Rain wets the surface of a drained field: dielectric constant rises and
    # so does backscatter, toward but not to the flooded response.
    if rain_mm > 20 and w < 0.5:
        vv += min(1.6, 0.05 * (rain_mm - 20))
    vh = expected_vh_db(stage) + 0.8 * w * stage

    vv += SPECKLE_SIGMA_DB * _speckle(plot_key, day, "vv")
    vh += SPECKLE_SIGMA_DB * _speckle(plot_key, day, "vh")
    # Undo the normalisation the detector will apply, so the pass carries the
    # slant-range value a granule actually holds.
    vv += INCIDENCE_SLOPE_DB_PER_DEG * (incidence_deg - REFERENCE_INCIDENCE_DEG)
    vh += INCIDENCE_SLOPE_DB_PER_DEG * (incidence_deg - REFERENCE_INCIDENCE_DEG)
    return SarPass(day=day, vv_db=vv, vh_db=vh, incidence_deg=incidence_deg,
                   relative_orbit=relative_orbit)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

@dataclass
class Classification:
    """What one pass was judged to be, and how strongly."""

    day: date
    state: WaterState
    p_flooded: float
    stage_estimate: float
    separation_db: float
    vv_normalised_db: float
    note: str = ""
    inferred: bool = False
    mixed_orbit: bool = False

    #: What an inferred call is worth against one the radar actually
    #: resolved. Interpolation is evidence, but it is weaker evidence, and a
    #: dry spell held together by it should score lower than one that was
    #: seen.
    INFERRED_DISCOUNT = 0.6

    @property
    def confidence(self) -> float:
        """Distance from an even call. AMBIGUOUS has none by construction."""
        if self.state is WaterState.AMBIGUOUS:
            return 0.0
        raw = abs(self.p_flooded - 0.5) * 2
        return raw * self.INFERRED_DISCOUNT if self.inferred else raw

    def to_dict(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "state": self.state.value,
            "p_flooded": round(self.p_flooded, 4),
            "confidence": round(self.confidence, 4),
            "stage_estimate": round(self.stage_estimate, 3),
            "separation_db": round(self.separation_db, 2),
            "vv_db": round(self.vv_normalised_db, 2),
            "inferred": self.inferred,
            "mixed_orbit": self.mixed_orbit,
            "note": self.note,
        }


@dataclass
class WaterRegimeDetector:
    """Classify each pass as flooded or drained, stage by stage.

    Takes backscatter and nothing else. The stage estimate comes from VH, the
    decision from VV against that stage's two expected responses, and the
    refusal from the two being too close to tell apart.
    """

    #: Below this the call is not trusted enough to count towards an AWD
    #: event. A regime built from 55% calls is a regime built from noise.
    min_confidence: float = 0.55
    speckle_sigma_db: float = SPECKLE_SIGMA_DB
    min_separation_db: float = MIN_SEPARATION_DB

    def stage_from_vh(self, p: SarPass) -> float:
        """Canopy stage in [0, 1] from cross-polarised backscatter."""
        stage = (p.vh_normalised_db + 26.0) / 11.5
        return max(0.0, min(1.0, stage))

    def classify_one(self, p: SarPass) -> Classification:
        stage = self.stage_from_vh(p)
        wet = flooded_vv_db(stage)
        dry = drained_vv_db(stage)
        separation = abs(wet - dry)
        vv = p.vv_normalised_db

        if separation < self.min_separation_db:
            return Classification(
                day=p.day, state=WaterState.AMBIGUOUS, p_flooded=0.5,
                stage_estimate=stage, separation_db=separation,
                vv_normalised_db=vv,
                note=("flooded and drained responses are within "
                      f"{separation:.1f} dB at stage {stage:.2f}; the two "
                      f"states are not separable on this pass"))

        # Logistic on the log-likelihood ratio of two Gaussians of equal
        # variance, which reduces to a linear discriminant. The sign flips
        # with the crossover, and that is the point.
        midpoint = (wet + dry) / 2
        scale = max(0.3, self.speckle_sigma_db)
        z = (vv - midpoint) / scale * (1.0 if wet > dry else -1.0)
        p_flooded = 1 / (1 + math.exp(-z))

        state = WaterState.FLOODED if p_flooded >= 0.5 else WaterState.DRAINED
        note = ""
        if abs(p_flooded - 0.5) * 2 < self.min_confidence:
            state = WaterState.AMBIGUOUS
            note = (f"call was {p_flooded:.0%} flooded, below the "
                    f"{self.min_confidence:.0%} confidence floor")
        return Classification(day=p.day, state=state, p_flooded=p_flooded,
                              stage_estimate=stage, separation_db=separation,
                              vv_normalised_db=vv, note=note)

    #: How much VV may move between two passes and still be the same surface
    #: state. Two speckle draws plus a little dielectric drift.
    max_persistence_step_db: float = 1.8

    def infer_across_gaps(self, calls: list[Classification]
                          ) -> list[Classification]:
        """Fill unreadable passes from their neighbours, where it is safe.

        The absolute levels overlap around the crossover stage, but the field
        is its own control and it does not change state silently: if the pass
        before and the pass after were both confidently flooded, and VV moved
        less than speckle, the field did not drain in between.

        Both neighbours must agree and both steps must be small. A gap
        between a flooded pass and a drained one is a transition, and a
        transition is exactly what must not be invented -- an AWD event
        conjured out of an unreadable pass is the failure this whole module
        exists to avoid.
        """
        for i, call in enumerate(calls):
            if call.state is not WaterState.AMBIGUOUS:
                continue
            before = next((c for c in reversed(calls[:i])
                           if c.state is not WaterState.AMBIGUOUS), None)
            after = next((c for c in calls[i + 1:]
                          if c.state is not WaterState.AMBIGUOUS), None)
            if before is None or after is None or before.state is not after.state:
                continue
            if (abs(call.vv_normalised_db - before.vv_normalised_db)
                    > self.max_persistence_step_db):
                continue
            if (abs(call.vv_normalised_db - after.vv_normalised_db)
                    > self.max_persistence_step_db):
                continue
            call.state = before.state
            call.p_flooded = (before.p_flooded + after.p_flooded) / 2
            call.inferred = True
            call.note = (
                "not separable on this pass; state carried across from "
                f"{before.day.isoformat()} and {after.day.isoformat()}, "
                f"which agree and are within "
                f"{self.max_persistence_step_db:.1f} dB")
        return calls

    def classify(self, passes: list[SarPass]) -> list[Classification]:
        orbits = {p.relative_orbit for p in passes}
        out = [self.classify_one(p) for p in sorted(passes, key=lambda x: x.day)]
        out = self.infer_across_gaps(out)
        if len(orbits) > 1:
            # Normalisation handles the mean shift; what it cannot remove is
            # that different geometries see a row-planted canopy differently.
            # Flagged on the calls so the season can report it once, rather
            # than repeating it on every line a reviewer reads.
            for c in out:
                c.mixed_orbit = True
        return out


# ---------------------------------------------------------------------------
# From passes to a water regime
# ---------------------------------------------------------------------------

@dataclass
class DrySpell:
    """A run of drained passes, which is what AWD actually is."""

    start: date
    end: date
    passes: int
    mean_confidence: float
    spanned_ambiguous: int = 0
    terminal: bool = False
    """The end-of-season drain before harvest. Real, detected, and *not* an
    AWD event: the baseline field is drained for harvest too, so crediting it
    would credit something the counterfactual also did."""

    @property
    def days(self) -> int:
        return (self.end - self.start).days + S1_REVISIT_DAYS

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(), "end": self.end.isoformat(),
            "days": self.days, "passes": self.passes,
            "mean_confidence": round(self.mean_confidence, 3),
            "spanned_ambiguous": self.spanned_ambiguous,
            "terminal": self.terminal,
        }


@dataclass
class RegimeSummary:
    """One season's water regime, as detected.

    `adoption_confidence` is what quantification multiplies area by, and it
    is deliberately not a yes. A season seen twelve times with three clean
    dry-downs and a season seen four times with one are not the same
    evidence, and crediting them alike is how a rice project over-credits
    without anyone lying.
    """

    season: str
    year: int
    start: date
    end: date
    passes: int
    usable_passes: int
    flooded_passes: int
    drained_passes: int
    ambiguous_passes: int
    spells: list[DrySpell] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Set on a year-level roll-up: the seasons it was built from.
    seasons: list["RegimeSummary"] = field(default_factory=list)
    #: Set on a roll-up, where the confidence is a weighted combination
    #: rather than this record's own spells.
    confidence_override: float | None = None

    #: AWD is a *repeated* wet-dry cycle. One drain is a drain.
    target_events: int = 3
    #: One confident pass bounds the drainage to somewhere between a day and
    #: two revisits. Safe AWD drains for five to ten days before re-flooding,
    #: so demanding two passes would reject the practice as it is actually
    #: taught.
    min_spell_days: int = S1_REVISIT_DAYS
    #: What a single-pass spell must score to count on its own. Two passes
    #: corroborate each other; one has to be clean.
    single_pass_confidence: float = 0.80

    @property
    def qualifying_spells(self) -> list[DrySpell]:
        """Spells that count as AWD events.

        Not the harvest drain, long enough to be a drainage rather than a
        blip, and -- where only one pass saw it -- clean enough that a single
        misclassification cannot manufacture an event.
        """
        return [s for s in self.spells
                if not s.terminal
                and s.days >= self.min_spell_days
                and (s.passes >= 2
                     or s.mean_confidence >= self.single_pass_confidence)]

    @property
    def coverage(self) -> float:
        return self.usable_passes / self.passes if self.passes else 0.0

    @property
    def drained_fraction(self) -> float:
        called = self.flooded_passes + self.drained_passes
        return self.drained_passes / called if called else 0.0

    @property
    def adoption_confidence(self) -> float:
        """Coverage and events, the same shape the optical path used.

        Kept deliberately parallel so the two are comparable: what changed is
        that the event count is now detected rather than asserted, and
        coverage is what the radar actually delivered rather than what the
        cloud left behind.
        """
        if self.confidence_override is not None:
            return self.confidence_override
        events = min(1.0, len(self.qualifying_spells) / self.target_events)
        quality = (sum(s.mean_confidence for s in self.qualifying_spells)
                   / len(self.qualifying_spells)) if self.qualifying_spells else 0.0
        return max(0.0, min(1.0, 0.35 * self.coverage
                            + 0.50 * events + 0.15 * quality))

    def report(self) -> Calculation:
        c = Calculation(f"detected water regime, {self.season} {self.year}",
                        "confidence")
        c.cite("Sentinel-1 C-band IW, VV+VH, 6-day revisit")
        c.cite("VM0051 v1.1: the baseline water regime is monitored, not "
               "assumed")
        c.add("passes in season", float(self.passes), "acquisitions")
        c.add("usable passes", float(self.usable_passes), "acquisitions",
              f"{self.ambiguous_passes} not separable at their crop stage")
        c.add("coverage", self.coverage, "fraction")
        c.add("passes called drained", float(self.drained_passes), "passes")
        c.add("qualifying dry spells", float(len(self.qualifying_spells)),
              "events", f"runs of >= {self.min_spell_days} days")
        c.add("AWD target", float(self.target_events), "events")
        c.finish(self.adoption_confidence)
        return c

    def to_dict(self) -> dict:
        return {
            "season": self.season, "year": self.year,
            "start": self.start.isoformat(), "end": self.end.isoformat(),
            "passes": self.passes, "usable_passes": self.usable_passes,
            "flooded_passes": self.flooded_passes,
            "drained_passes": self.drained_passes,
            "ambiguous_passes": self.ambiguous_passes,
            "coverage": round(self.coverage, 4),
            "drained_fraction": round(self.drained_fraction, 4),
            "spells": [s.to_dict() for s in self.spells],
            "qualifying_spells": len(self.qualifying_spells),
            "adoption_confidence": round(self.adoption_confidence, 4),
            "warnings": list(self.warnings),
            "seasons": [s.to_dict() for s in self.seasons],
        }


def dry_spells(calls: list[Classification], *,
               min_confidence: float = 0.55) -> list[DrySpell]:
    """Group consecutive drained calls into spells.

    An ambiguous pass in the middle of a run does not end it -- the field did
    not re-flood, the radar could not tell -- but it is counted and reported,
    because a spell held together by a pass nobody could read is weaker
    evidence than one that was seen throughout.
    """
    spells: list[DrySpell] = []
    run: list[Classification] = []
    spanned = 0
    pending_ambiguous = 0

    def close() -> None:
        nonlocal run, spanned, pending_ambiguous
        if run:
            spells.append(DrySpell(
                start=run[0].day, end=run[-1].day, passes=len(run),
                mean_confidence=sum(c.confidence for c in run) / len(run),
                spanned_ambiguous=spanned))
        run = []
        spanned = 0
        pending_ambiguous = 0

    for call in sorted(calls, key=lambda c: c.day):
        if call.state is WaterState.DRAINED and call.confidence >= min_confidence:
            if run:
                spanned += pending_ambiguous
            pending_ambiguous = 0
            run.append(call)
        elif call.state is WaterState.AMBIGUOUS:
            if run:
                pending_ambiguous += 1
            # Two unreadable passes in a row is a gap, not a spell.
            if pending_ambiguous >= 2:
                close()
        else:
            close()
    close()
    return spells


def _mark_terminal(spells: list[DrySpell],
                   calls: list[Classification]) -> None:
    """Flag the harvest drain, which is not an AWD event.

    Every paddy is drained before harvest, in the project and in the
    baseline alike, so counting it would credit the counterfactual. The
    detector has no crop calendar -- it has the canopy stage it estimated
    from VH, which rises to a peak and falls as the crop senesces. A spell
    that begins after that peak and runs to the last pass of the season is
    the harvest drain.
    """
    if not spells or not calls:
        return
    ordered = sorted(calls, key=lambda c: c.day)
    peak = max(ordered, key=lambda c: c.stage_estimate)
    last_day = ordered[-1].day
    for spell in spells:
        if spell.start > peak.day and spell.end == last_day:
            spell.terminal = True


def summarise_regime(calls: list[Classification], *, season: str, year: int,
                     min_confidence: float = 0.55,
                     target_events: int = 3) -> RegimeSummary:
    """Reduce a season of classified passes to what quantification needs."""
    calls = sorted(calls, key=lambda c: c.day)
    if not calls:
        raise ValueError("no passes to summarise")

    flooded = sum(1 for c in calls if c.state is WaterState.FLOODED)
    drained = sum(1 for c in calls if c.state is WaterState.DRAINED)
    ambiguous = sum(1 for c in calls if c.state is WaterState.AMBIGUOUS)

    spells = dry_spells(calls, min_confidence=min_confidence)
    _mark_terminal(spells, calls)

    summary = RegimeSummary(
        season=season, year=year, start=calls[0].day, end=calls[-1].day,
        passes=len(calls), usable_passes=flooded + drained,
        flooded_passes=flooded, drained_passes=drained,
        ambiguous_passes=ambiguous, spells=spells,
        target_events=target_events)

    if any(c.mixed_orbit for c in calls):
        summary.warnings.append(
            "the series mixes relative orbits; incidence angle is normalised "
            "but a row-planted canopy still looks different from a different "
            "geometry")
    if summary.coverage < 0.7:
        summary.warnings.append(
            f"{summary.coverage:.0%} of passes were separable; the rest fell "
            f"near the stage where flooded and drained backscatter cross")
    if not summary.qualifying_spells:
        summary.warnings.append(
            "no dry spell of the minimum length was detected; on the "
            "evidence this season was continuously flooded")
    rejected = [s for s in summary.spells
                if not s.terminal and s not in summary.qualifying_spells]
    if rejected:
        summary.warnings.append(
            f"{len(rejected)} drainage(s) seen but not counted as AWD "
            f"events: too short, or seen by a single pass that was not "
            f"clean enough to stand alone")
    if any(s.terminal for s in summary.spells):
        summary.warnings.append(
            "the end-of-season drain before harvest was detected and "
            "excluded; the baseline field is drained for harvest too")
    spanned = sum(s.spanned_ambiguous for s in summary.qualifying_spells)
    if spanned:
        summary.warnings.append(
            f"{spanned} unreadable pass(es) sit inside counted dry spells")
    return summary


def _roll_up(regimes: list[RegimeSummary]) -> RegimeSummary:
    """Combine a year's seasons into one record quantification can read."""
    regimes = sorted(regimes, key=lambda r: r.start)
    if len(regimes) == 1:
        only = regimes[0]
        only.seasons = [only]
        return only

    weight = sum(r.passes for r in regimes) or 1
    blended = sum(r.adoption_confidence * r.passes for r in regimes) / weight

    rolled = RegimeSummary(
        season=" + ".join(r.season for r in regimes),
        year=regimes[0].year, start=regimes[0].start, end=regimes[-1].end,
        passes=sum(r.passes for r in regimes),
        usable_passes=sum(r.usable_passes for r in regimes),
        flooded_passes=sum(r.flooded_passes for r in regimes),
        drained_passes=sum(r.drained_passes for r in regimes),
        ambiguous_passes=sum(r.ambiguous_passes for r in regimes),
        spells=[s for r in regimes for s in r.spells],
        target_events=regimes[0].target_events)
    rolled.seasons = regimes
    rolled.confidence_override = blended
    for r in regimes:
        rolled.warnings.extend(f"{r.season}: {w}" for w in r.warnings)
    weakest = min(regimes, key=lambda r: r.adoption_confidence)
    if weakest.adoption_confidence < 0.4:
        rolled.warnings.insert(0, (
            f"{weakest.season} scored "
            f"{weakest.adoption_confidence:.0%} on its own; the year is "
            f"carried by the other season and this one needs review"))
    return rolled


# ---------------------------------------------------------------------------
# Scoring -- for tests and for a validation report, never for crediting
# ---------------------------------------------------------------------------

def score(calls: list[Classification],
          truth: dict[date, bool]) -> dict:
    """How well the detector recovered a known water state.

    `truth[day]` is True where the field was flooded. Ambiguous calls are
    reported separately rather than counted as errors: refusing to call a
    pass is a different act from calling it wrong, and a detector punished
    for abstaining will stop abstaining.
    """
    tp = fp = tn = fn = 0
    abstained = 0
    for call in calls:
        if call.day not in truth:
            continue
        actually_flooded = truth[call.day]
        if call.state is WaterState.AMBIGUOUS:
            abstained += 1
        elif call.state is WaterState.FLOODED:
            if actually_flooded:
                tp += 1
            else:
                fp += 1
        else:
            if actually_flooded:
                fn += 1
            else:
                tn += 1

    called = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "called": called,
        "abstained": abstained,
        "accuracy": (tp + tn) / called if called else 0.0,
        "precision_flooded": precision,
        "recall_flooded": recall,
        "f1_flooded": (2 * precision * recall / (precision + recall)
                       if (precision + recall) else 0.0),
        "drained_accuracy": tn / (tn + fp) if (tn + fp) else 0.0,
        "true_positive": tp, "false_positive": fp,
        "true_negative": tn, "false_negative": fn,
    }


# ---------------------------------------------------------------------------
# Serving the regime to quantification
# ---------------------------------------------------------------------------

class SarProvider:
    """Serves detected adoption through the standard `Provider` interface.

    The methodology asks for `practice_adopted` and gets a probability that
    came from radar, not from a configuration dictionary. Swapping this for a
    client that reads real granules changes nothing above it, which is the
    only reason the interface exists.
    """

    name = "sentinel1"

    def __init__(self, regimes: dict[int, RegimeSummary]):
        self._by_year = dict(regimes)

    @classmethod
    def from_passes(cls, seasons: dict[tuple[int, str], list[SarPass]], *,
                    detector: WaterRegimeDetector | None = None,
                    target_events: int = 3) -> "SarProvider":
        """Detect every season, and roll the seasons up into a year.

        A rice year is two seasons and a vintage is annual, so the two have
        to be combined. Weighted by **baseline exposure** -- here the number
        of acquisitions the season ran for, since the counterfactual field is
        flooded throughout either way -- and never by achieved abatement. A
        lapsed season abates nothing, so an abatement-weighted average gives
        it zero weight and it disappears from the year entirely, which is
        exactly how a project over-credits without anyone deciding to.
        """
        detector = detector or WaterRegimeDetector()
        per_season: dict[int, list[RegimeSummary]] = {}
        for (year, season), passes in sorted(seasons.items()):
            if not passes:
                continue
            per_season.setdefault(year, []).append(summarise_regime(
                detector.classify(passes), season=season, year=year,
                min_confidence=detector.min_confidence,
                target_events=target_events))
        return cls({y: _roll_up(rs) for y, rs in per_season.items()})

    def regime(self, year: int) -> RegimeSummary | None:
        return self._by_year.get(year)

    def seasons(self, year: int) -> list[RegimeSummary]:
        regime = self._by_year.get(year)
        return list(regime.seasons) if regime else []

    def warnings_for(self, year: int) -> list[str]:
        regime = self._by_year.get(year)
        return list(regime.warnings) if regime else []

    def retrieve(self, plot, variable: str, on: date):
        from .remote_sensing import Retrieval

        if variable != "practice_adopted":
            return None
        regime = self._by_year.get(on.year)
        if regime is None:
            return None
        return Retrieval(plot.id, variable, regime.adoption_confidence,
                         "probability",
                         max(0.05, 1 - regime.adoption_confidence),
                         regime.end, self.name)
