"""What every methodology has in common, and where they are allowed to differ.

A methodology's job is to turn monitored observations into a defensible number
of credits. The shape of that job is always the same -- establish a baseline,
measure the project, take the difference, deduct for what you do not know and
for what could be reversed -- so that shape lives here, and only the
pathway-specific parts live in the individual modules.

Deductions are modelled as first-class objects rather than inline multipliers
because a verifier reads them one at a time, and because the order they are
applied in changes the answer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from ..audit import Calculation
from ..domain import Project
from ..remote_sensing import Provider


@dataclass(frozen=True)
class Deduction:
    """A withholding applied to gross abatement, as a fraction."""

    name: str
    fraction: float
    basis: str

    def apply(self, amount: float) -> float:
        return amount * self.fraction


@dataclass
class VintageResult:
    """One reporting year's worth of credits, and why."""

    project_id: str
    methodology: str
    year: int
    area_ha: float
    gross_t: float
    deductions: list[tuple[Deduction, float]] = field(default_factory=list)
    net_t: float = 0.0
    relative_uncertainty: float = 0.0
    calculations: list[Calculation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    excluded_plots: dict[str, list[str]] = field(default_factory=dict)

    @property
    def t_per_ha(self) -> float:
        return self.net_t / self.area_ha if self.area_ha else 0.0

    @property
    def total_deducted(self) -> float:
        return sum(amount for _, amount in self.deductions)

    def render(self) -> str:
        lines = [
            f"{self.methodology} - {self.project_id} - vintage {self.year}",
            "=" * 72,
            f"  creditable area            {self.area_ha:>14,.1f} ha",
            f"  gross abatement            {self.gross_t:>14,.1f} tCO2e",
        ]
        for d, amount in self.deductions:
            lines.append(f"  - {d.name:<25} {-amount:>14,.1f} tCO2e   ({d.basis})")
        lines += [
            "  " + "-" * 70,
            f"  net issuable               {self.net_t:>14,.1f} tCO2e",
            f"                             {self.t_per_ha:>14,.2f} tCO2e/ha",
        ]
        if self.excluded_plots:
            lines.append(f"  excluded plots: {len(self.excluded_plots)}")
        for w in self.warnings:
            lines.append(f"  ! {w}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "methodology": self.methodology,
            "year": self.year,
            "area_ha": round(self.area_ha, 4),
            "gross_t": round(self.gross_t, 4),
            "deductions": [
                {"name": d.name, "fraction": d.fraction,
                 "basis": d.basis, "amount_t": round(a, 4)}
                for d, a in self.deductions
            ],
            "net_t": round(self.net_t, 4),
            "relative_uncertainty": round(self.relative_uncertainty, 4),
            "warnings": list(self.warnings),
            "excluded_plots": self.excluded_plots,
            "calculations": [c.to_dict() for c in self.calculations],
        }


class Methodology(Protocol):
    """The contract a pathway implements."""

    id: str
    name: str

    def quantify(self, project: Project, provider: Provider,
                 reporting_year: int) -> VintageResult:
        ...


# ---------------------------------------------------------------------------
# Shared deduction rules
# ---------------------------------------------------------------------------

UNCERTAINTY_ALLOWANCE = 0.15
"""VCS allows 15% relative uncertainty at the 90% confidence level before it
starts deducting. Below the allowance, nothing is withheld; above it, the
excess comes straight off the top. This is the single strongest financial
argument for locally calibrated allometry."""


def uncertainty_deduction(relative_uncertainty: float,
                          allowance: float = UNCERTAINTY_ALLOWANCE) -> Deduction:
    excess = max(0.0, relative_uncertainty - allowance)
    return Deduction(
        name="uncertainty",
        fraction=excess,
        basis=f"{relative_uncertainty:.1%} relative uncertainty vs "
              f"{allowance:.0%} allowance",
    )


def combine_uncertainty(sigmas: list[float], total: float) -> float:
    """Relative uncertainty of a sum of partly independent parts.

    Errors across plots are correlated -- they share one allometric equation
    and one retrieval model -- so treating them as independent would divide the
    error by sqrt(n) and flatter the project into a deduction it has not
    earned. We split the difference: independent within, correlated across.
    """
    if total <= 0 or not sigmas:
        return 0.0
    independent = math.sqrt(sum(s ** 2 for s in sigmas))
    correlated = sum(sigmas)
    blended = math.sqrt(independent * correlated)
    return blended / total


def apply_deductions(gross: float, deductions: list[Deduction]) -> tuple[float, list[tuple[Deduction, float]]]:
    """Apply in order, each to the running remainder.

    Sequential, not summed: a 15% uncertainty deduction followed by a 20%
    buffer withholds 32%, not 35%. Getting this backwards is a common and
    expensive spreadsheet error.
    """
    remaining = gross
    applied: list[tuple[Deduction, float]] = []
    for d in deductions:
        amount = d.apply(remaining)
        applied.append((d, amount))
        remaining -= amount
    return remaining, applied


def reporting_date(year: int) -> date:
    """Monitoring is anchored to the end of the reporting year."""
    return date(year, 12, 31)
