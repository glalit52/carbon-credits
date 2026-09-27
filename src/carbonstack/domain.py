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


class RiceEcosystem(str, Enum):
    """Rice water regime. VM0051 credits only irrigated lowland.

    Upland, rainfed and deepwater systems are outside any project's control
    over the water table, so the methodology excludes them outright. Recording
    this at enrolment is what stops an ineligible field reaching quantification.
    """

    IRRIGATED_LOWLAND = "irrigated_lowland"
    RAINFED = "rainfed"
    UPLAND = "upland"
    DEEPWATER = "deepwater"
    UNKNOWN = "unknown"

    @property
    def vm0051_eligible(self) -> bool:
        return self is RiceEcosystem.IRRIGATED_LOWLAND


class WaterControl(str, Enum):
    """Whether the farmer can actually drain the field when the plan says to.

    AWD is not a practice you can adopt without drainage control, so a field
    with no control cannot deliver the abatement however good the intention.
    """

    FULL = "full"           # irrigation and drainage both controlled
    IRRIGATION_ONLY = "irrigation_only"
    NONE = "none"
    UNKNOWN = "unknown"

    @property
    def sufficient_for_awd(self) -> bool:
        return self is WaterControl.FULL


@dataclass
class CarbonRights:
    """The right to the credits, which is not the same as consent to data.

    Enrolment that captures only a data-use consent leaves the project unable
    to show a registry who owns the carbon. Both Verra and Gold Standard ask
    for evidence that the proponent holds the right, and for the farmer to
    have been told what a reversal means for them.
    """

    agreement_reference: str
    signed_on: date
    holder: str                          # who holds the right to the credits
    reversal_clause_ack: bool = False    # farmer was told about reversals
    expires_on: date | None = None

    def issues(self, on: date | None = None) -> list[str]:
        problems: list[str] = []
        if not self.agreement_reference.strip():
            problems.append("carbon rights agreement has no reference")
        if not self.holder.strip():
            problems.append("carbon rights agreement names no holder")
        if not self.reversal_clause_ack:
            problems.append("farmer has not acknowledged the reversal clause")
        if self.expires_on and self.expires_on < (on or date.today()):
            problems.append(f"carbon rights agreement expired {self.expires_on}")
        return problems


@dataclass
class StakeholderConsultation:
    """Local consultation and a grievance channel.

    Required by both Verra and Gold Standard, and absent from the product
    until now. A project can be scientifically perfect and still fail
    validation on this.
    """

    held_on: date
    record_reference: str
    participants: int = 0
    grievance_channel: str = ""

    def issues(self) -> list[str]:
        problems: list[str] = []
        if not self.record_reference.strip():
            problems.append("stakeholder consultation has no record reference")
        if self.participants <= 0:
            problems.append("stakeholder consultation records no participants")
        if not self.grievance_channel.strip():
            problems.append("no grievance channel recorded")
        return problems


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
    carbon_rights: CarbonRights | None = None

    @property
    def consent_valid(self) -> bool:
        return self.consent_on is not None and bool(self.consent_reference)

    def carbon_rights_issues(self, on: date | None = None) -> list[str]:
        """Consent to use data is not a right to sell the carbon."""
        if self.carbon_rights is None:
            return ["no carbon rights agreement on file"]
        return self.carbon_rights.issues(on)


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

    # Additionality timing. A baseline has to be measured before the practice
    # changes; a farmer already practising AWD has no counterfactual left to
    # measure, and the eligible pool shrinks every season this is not captured.
    baseline_captured_on: date | None = None
    practice_started_on: date | None = None

    # Rice attributes. Recorded at enrolment because VM0051 eligibility turns
    # on them, and discovering an ineligible field at verification is a season
    # of monitoring spent on nothing.
    ecosystem: "RiceEcosystem | None" = None
    water_control: "WaterControl | None" = None

    @property
    def vintage_year(self) -> int:
        return self.enrolled_on.year

    def additionality_issues(self) -> list[str]:
        """Was the baseline captured before the practice changed?"""
        problems: list[str] = []
        if self.baseline_captured_on is None:
            problems.append("no baseline capture date recorded")
            return problems
        if self.practice_started_on is None:
            return problems
        if self.practice_started_on < self.baseline_captured_on:
            problems.append(
                f"practice started {self.practice_started_on}, before the baseline "
                f"was captured {self.baseline_captured_on} -- no valid "
                f"counterfactual, additionality is at risk")
        return problems


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
    methodology_version: str = ""
    """Pinned per project. VM0042 v2.2 took corrections in June 2026 and a
    major revision is in progress; a project that does not say which version
    it was quantified under cannot be reproduced or defended."""

    consultation: StakeholderConsultation | None = None
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
        by_plot = {e.plot_id: e for e in self.enrollments}

        for pid in sorted(by_plot):
            plot = self.plots[pid]
            problems = plot.issues()
            farmer = self.farmers.get(plot.farmer_id)
            if farmer is None:
                problems.append("plot has no farmer record")
            else:
                if not farmer.consent_valid:
                    problems.append("farmer consent missing or unreferenced")
                problems += farmer.carbon_rights_issues()
            problems += by_plot[pid].additionality_issues()
            if problems:
                report[pid] = problems
        return report

    def programme_issues(self) -> list[str]:
        """Problems with the project as a whole, not with any one plot.

        These block validation for every hectare at once, which is why they
        are reported separately rather than repeated against each plot.
        """
        problems: list[str] = []
        if not self.methodology_version:
            problems.append(
                "no methodology version pinned -- the quantification cannot be "
                "reproduced against a specific version of the rules")
        if self.consultation is None:
            problems.append(
                "no local stakeholder consultation on record -- required by "
                "both Verra and Gold Standard")
        else:
            problems += self.consultation.issues()
        return problems

    def creditable_plot_ids(self) -> set[str]:
        blocked = set(self.eligibility_issues())
        return {e.plot_id for e in self.enrollments} - blocked

    def creditable_area_ha(self) -> float:
        return sum(self.plots[p].area_ha for p in self.creditable_plot_ids())
