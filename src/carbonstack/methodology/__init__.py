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

_REGISTRY: dict[str, type] = {
    VM0047.id: VM0047,
    VM0042.id: VM0042,
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


__all__ = [
    "get", "available", "Methodology", "VintageResult", "Deduction",
    "VM0047", "VM0042", "uncertainty_deduction", "combine_uncertainty",
    "apply_deductions",
]
