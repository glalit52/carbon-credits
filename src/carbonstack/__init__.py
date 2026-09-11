"""carbonstack - a dMRV core for land-based carbon projects.

Design target, set by model/carbon_model.py: marginal monitoring cost must
stay under ~$6 per hectare per year, because that is the entire developer
margin on a cropland hectare. Everything here follows from that -- routine
monitoring is satellite-first and batch-processed, with no per-plot human
step, and field visits exist to calibrate the model rather than to produce
the numbers.

The second principle is that a credit is only worth what its evidence is
worth. Every quantity this package computes carries a Calculation: the
inputs, the equation, the intermediate terms and the deductions, in order.
A verifier should be able to read it without reading the source.
"""

__version__ = "0.1.0"

from .domain import (
    Cohort,
    Enrollment,
    Farmer,
    Observation,
    Plot,
    Project,
    TrackKind,
)
from .audit import Calculation, Term

__all__ = [
    "Project", "Plot", "Farmer", "Enrollment", "Cohort", "Observation",
    "TrackKind", "Calculation", "Term", "__version__",
]
