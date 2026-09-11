"""The monitoring layer, and the reason the unit economics can work.

model/carbon_model.py puts the ceiling on monitoring at roughly $6 per
hectare per year for a cropland hectare. A field visit blows that on one
plot. A satellite retrieval costs the same for ten plots as for ten
thousand, which is the only reason a smallholder portfolio closes at all.

Providers are swappable on purpose. The synthetic provider below makes the
whole pipeline runnable and testable today; a Sentinel-2 + GEDI provider
drops into the same interface without touching quantification. Field plots
enter through the same interface too, as a high-trust provider used to
calibrate the cheap one -- never as the routine source.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from .domain import Plot


@dataclass(frozen=True)
class Retrieval:
    """One monitored value for one plot, with its provenance and error."""

    plot_id: str
    variable: str
    value: float
    unit: str
    uncertainty: float
    observed_on: date
    source: str

    @property
    def is_ground_truth(self) -> bool:
        return self.source in {"field_plot", "lidar_survey"}


@runtime_checkable
class Provider(Protocol):
    """Anything that can report a monitored variable for a plot on a date."""

    name: str

    def retrieve(self, plot: Plot, variable: str, on: date) -> Retrieval | None:
        ...


class SyntheticProvider:
    """A deterministic stand-in for a real earth-observation pipeline.

    Every value is a pure function of the plot's boundary fingerprint and the
    date, so runs are reproducible and tests do not need network or fixtures.
    It models plausible growth, not any real place -- it exists so the
    quantification path can be exercised end to end before the satellite
    pipeline lands, and so a regression in the engine shows up as a changed
    number rather than as a missing one.
    """

    name = "synthetic"

    def __init__(self, *, planting_year: int, peak_height_m: float = 14.0,
                 years_to_half: float = 6.0, steepness: float = 0.55):
        self.planting_year = planting_year
        self.peak_height_m = peak_height_m
        self.years_to_half = years_to_half
        self.steepness = steepness

    def _jitter(self, plot: Plot, salt: str) -> float:
        """Stable per-plot variation in [-1, 1]. Real landscapes are not uniform."""
        seed = hashlib.sha256(f"{plot.fingerprint}:{salt}".encode()).digest()
        return (int.from_bytes(seed[:4], "big") / 0xFFFFFFFF) * 2 - 1

    def canopy_height_m(self, plot: Plot, on: date) -> float:
        age = on.year - self.planting_year + (on.month - 1) / 12.0
        if age <= 0:
            return 0.0
        peak = self.peak_height_m * (1 + 0.18 * self._jitter(plot, "peak"))
        x = self.steepness * (age - self.years_to_half)
        x = max(-60.0, min(60.0, x))
        return peak / (1 + math.exp(-x))

    def retrieve(self, plot: Plot, variable: str, on: date) -> Retrieval | None:
        if variable == "canopy_height_m":
            h = self.canopy_height_m(plot, on)
            # Retrieval error is worse for short canopies -- a real and
            # awkward property of optical/lidar fusion that the uncertainty
            # deduction has to see.
            sigma = max(0.8, 0.18 * h) if h > 0 else 0.8
            return Retrieval(plot.id, variable, h, "m", sigma, on, self.name)

        if variable == "stocking_index":
            h = self.canopy_height_m(plot, on)
            si = min(1.0, h / self.peak_height_m)
            return Retrieval(plot.id, variable, si, "fraction",
                             max(0.03, 0.15 * si), on, self.name)

        if variable == "practice_adopted":
            # Detection of a practice event, e.g. an AWD dry-down. Expressed as
            # a probability so that partial adoption is representable; a hard
            # boolean here would quietly overstate every cropland project.
            p = 0.5 + 0.45 * self._jitter(plot, f"practice:{on.year}")
            return Retrieval(plot.id, variable, min(1.0, max(0.0, p)),
                             "probability", 0.1, on, self.name)

        return None


class FieldPlotProvider:
    """Measured plots, keyed by (plot_id, variable, year).

    High trust, high cost, low coverage. Used to calibrate and to challenge
    the satellite record -- if these two disagree beyond their error bars,
    that is a finding, not noise, and quantification should refuse to proceed.
    """

    name = "field_plot"

    def __init__(self, measurements: dict[tuple[str, str, int], tuple[float, float, str]]):
        self._m = measurements

    def retrieve(self, plot: Plot, variable: str, on: date) -> Retrieval | None:
        hit = self._m.get((plot.id, variable, on.year))
        if hit is None:
            return None
        value, sigma, unit = hit
        return Retrieval(plot.id, variable, value, unit, sigma, on, self.name)


def reconcile(satellite: Retrieval | None, field: Retrieval | None,
              *, sigma_threshold: float = 2.0) -> tuple[Retrieval | None, str | None]:
    """Prefer ground truth, but report disagreement rather than burying it.

    Returns (chosen retrieval, warning or None). A gap wider than the combined
    error bar means the model is wrong for this plot, and silently taking
    either number would be the beginning of an over-crediting story.
    """
    if field is None:
        return satellite, None
    if satellite is None:
        return field, None

    combined = math.sqrt(satellite.uncertainty ** 2 + field.uncertainty ** 2)
    gap = abs(satellite.value - field.value)
    if combined > 0 and gap > sigma_threshold * combined:
        return field, (
            f"plot {field.plot_id}: {field.variable} satellite {satellite.value:.2f} vs "
            f"field {field.value:.2f} -- {gap / combined:.1f} sigma apart, "
            f"model may be miscalibrated here"
        )
    return field, None
