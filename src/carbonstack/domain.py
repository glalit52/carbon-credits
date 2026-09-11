"""The entities a land-based carbon project is actually made of.

Modelled around what a verification body asks for, not around what is
convenient to store. The awkward parts of the schema -- consent evidence,
tenure basis, cohort vintages -- are awkward because verification is awkward,
and a schema that smooths them over just moves the problem to audit time.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .geo import Ring, area_ha, centroid, validate_ring


class TrackKind(str, Enum):
    """Which pathway a project runs. Drives methodology and crediting cadence."""

    ARR = "arr"                # afforestation / reforestation / revegetation
    AGROFORESTRY = "agroforestry"
    CROPLAND = "cropland"      # improved agricultural land management
    RICE = "rice"              # methane avoidance via water management


class TenureBasis(str, Enum):
    """How the project's right to the carbon is established.

    ARR is unfinanceable without this, so it is a required field rather than
    an optional attachment. See docs/research/01-mitti-labs-and-varaha.md.
    """

    OWNED_TITLE = "owned_title"
    REGISTERED_LEASE = "registered_lease"
    COMMUNITY_RIGHT = "community_right"     # e.g. forest rights recognition
    GRAMA_SABHA_CONSENT = "grama_sabha_consent"
    UNDOCUMENTED = "undocumented"           # blocks issuance; tracked, not hidden


@dataclass
class Farmer:
    id: str
    name: str
    village: str
    district: str
    state: str
    consent_on: date | None = None
    consent_reference: str = ""

    @property
    def consent_valid(self) -> bool:
        return self.consent_on is not None and bool(self.consent_reference)


@dataclass
class Plot:
    """A contiguous parcel under one tenure basis."""

    id: str
    farmer_id: str
    boundary: Ring
    tenure: TenureBasis
    tenure_reference: str = ""
    surveyed_on: date | None = None

    @property
    def area_ha(self) -> float:
        return area_ha(self.boundary)

    @property
    def centroid(self) -> tuple[float, float]:
        return centroid(self.boundary)

    @property
    def fingerprint(self) -> str:
        """Stable hash of the boundary.

        Lets us detect a boundary that was quietly redrawn between vintages --
        one of the easier ways for a project to over-credit without anyone
        intending to.
        """
        payload = ";".join(f"{lon:.7f},{lat:.7f}" for lon, lat in self.boundary)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def issues(self) -> list[str]:
        problems = validate_ring(self.boundary)
        if self.tenure is TenureBasis.UNDOCUMENTED:
            problems.append("tenure basis is undocumented")
        elif not self.tenure_reference:
            problems.append(f"tenure basis {self.tenure.value} has no reference document")
        return problems


@dataclass
class Enrollment:
    """A plot brought into a project on a date, under a practice."""

    plot_id: str
    project_id: str
    enrolled_on: date
    practice: str                  # e.g. "awd", "direct_seeded_rice", "block_planting"
    species: list[str] = field(default_factory=list)
    stems_planted: int | None = None

    @property
    def vintage_year(self) -> int:
        return self.enrolled_on.year


@dataclass
class Cohort:
    """Plots enrolled in the same year, which therefore age together.

    Credits depend on how long ago the intervention happened, so cohort is the
    unit that quantification iterates over -- not the project and not the plot.
    """

    year: int
    plot_ids: list[str] = field(default_factory=list)

    def age_in(self, reporting_year: int) -> int:
        return max(0, reporting_year - self.year + 1)


@dataclass
class Observation:
    """One monitored quantity for one plot at one time.

    Source is recorded because a verifier weights a satellite retrieval and a
    field measurement differently, and because our own uncertainty model has
    to know which is which.
    """

    plot_id: str
    observed_on: date
    variable: str                 # "canopy_height_m", "stocking_index", "soc_pct", ...
    value: float
    unit: str
    source: str                   # "sentinel2+gedi", "field_plot", "farmer_report"
    uncertainty: float | None = None   # 1 sigma, same unit

    @property
    def is_ground_truth(self) -> bool:
        return self.source in {"field_plot", "lidar_survey"}


@dataclass
class Project:
    id: str
    name: str
    track: TrackKind
    country: str
    start_date: date
    crediting_period_yrs: int = 30
    farmers: dict[str, Farmer] = field(default_factory=dict)
    plots: dict[str, Plot] = field(default_factory=dict)
    enrollments: list[Enrollment] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)

    # -- building -----------------------------------------------------------

    def add_farmer(self, farmer: Farmer) -> Farmer:
        self.farmers[farmer.id] = farmer
        return farmer

    def add_plot(self, plot: Plot) -> Plot:
        if plot.farmer_id not in self.farmers:
            raise KeyError(f"unknown farmer {plot.farmer_id!r}")
        self.plots[plot.id] = plot
        return plot

    def enroll(self, enrollment: Enrollment) -> Enrollment:
        if enrollment.plot_id not in self.plots:
            raise KeyError(f"unknown plot {enrollment.plot_id!r}")
        self.enrollments.append(enrollment)
        return enrollment

    def observe(self, observation: Observation) -> Observation:
        if observation.plot_id not in self.plots:
            raise KeyError(f"unknown plot {observation.plot_id!r}")
        self.observations.append(observation)
        return observation

    # -- reading ------------------------------------------------------------

    @property
    def area_ha(self) -> float:
        return sum(self.plots[e.plot_id].area_ha for e in self.enrollments)

    def cohorts(self) -> list[Cohort]:
        by_year: dict[int, list[str]] = {}
        for e in self.enrollments:
            by_year.setdefault(e.vintage_year, []).append(e.plot_id)
        return [Cohort(year=y, plot_ids=p) for y, p in sorted(by_year.items())]

    def cohort_area_ha(self, cohort: Cohort) -> float:
        return sum(self.plots[pid].area_ha for pid in cohort.plot_ids)

    def observations_for(self, plot_id: str, variable: str) -> list[Observation]:
        return sorted(
            (o for o in self.observations
             if o.plot_id == plot_id and o.variable == variable),
            key=lambda o: o.observed_on,
        )

    def latest_observation(self, plot_id: str, variable: str,
                           on_or_before: date | None = None) -> Observation | None:
        obs = self.observations_for(plot_id, variable)
        if on_or_before is not None:
            obs = [o for o in obs if o.observed_on <= on_or_before]
        return obs[-1] if obs else None

    # -- gates --------------------------------------------------------------

    def eligibility_issues(self) -> dict[str, list[str]]:
        """Everything that would block issuance, per plot.

        Run at enrolment and on every batch. A plot that fails here still
        exists in the project -- it is simply excluded from the creditable
        area, which is both honest and what the methodology requires.
        """
        report: dict[str, list[str]] = {}
        enrolled = {e.plot_id for e in self.enrollments}

        for pid in sorted(enrolled):
            plot = self.plots[pid]
            problems = plot.issues()
            farmer = self.farmers.get(plot.farmer_id)
            if farmer is None:
                problems.append("plot has no farmer record")
            elif not farmer.consent_valid:
                problems.append("farmer consent missing or unreferenced")
            if problems:
                report[pid] = problems
        return report

    def creditable_plot_ids(self) -> set[str]:
        blocked = set(self.eligibility_issues())
        return {e.plot_id for e in self.enrollments} - blocked

    def creditable_area_ha(self) -> float:
        return sum(self.plots[p].area_ha for p in self.creditable_plot_ids())
