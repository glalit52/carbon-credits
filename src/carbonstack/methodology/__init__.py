"""Methodology plugins.

Registered by id so a project can name its methodology in configuration and
the engine resolves it, rather than importing a specific module. Adding a
pathway means adding a module here and nothing else.
"""

from __future__ import annotations

from .base import (
    Deduction,
    Methodology,
    VintageResult,
    apply_deductions,
    combine_uncertainty,
    uncertainty_deduction,
)
from .vm0042 import VM0042
from .vm0047 import VM0047
from .vm0051 import VM0051
from .vm0042_soil import VM0042Soil
from .vm0047_census import VM0047Census

_REGISTRY: dict[str, type] = {
    VM0047.id: VM0047,
    VM0042.id: VM0042,
    VM0051.id: VM0051,
}


def get(methodology_id: str, **kwargs):
    """Resolve a methodology by id, e.g. get("VM0047", buffer_fraction=0.20)."""
    try:
        cls = _REGISTRY[methodology_id.upper()]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"unknown methodology {methodology_id!r}; known: {known}") from None
    return cls(**kwargs)


def available() -> list[str]:
    return sorted(_REGISTRY)


def soil_pathway(**kwargs) -> VM0042Soil:
    """VM0042's measure-and-model soil pathway.

    Kept out of `_REGISTRY` deliberately. Every methodology in there takes a
    `Provider` and asks it for a number; soil takes physical cores, a lab
    reference and a VMD0053 validation report, so its `quantify` has a
    different signature and resolving it by id would hand callers something
    they cannot drive the same way.
    """
    return VM0042Soil(**kwargs)


def census_pathway(**kwargs) -> VM0047Census:
    """VM0047's census-based approach, for scattered trees.

    Out of `_REGISTRY` for the same reason as the soil pathway: it takes a
    census inventory rather than a `Provider`. The choice between this and the
    area-based path in the registry is dictated by what is planted -- a
    stocking index has nothing to measure over a bund line.
    """
    return VM0047Census(**kwargs)


__all__ = [
    "get", "available", "Methodology", "VintageResult", "Deduction",
    "VM0047", "VM0042", "VM0051", "VM0042Soil", "soil_pathway",
    "VM0047Census", "census_pathway",
    "uncertainty_deduction", "combine_uncertainty",
    "apply_deductions",
]
