"""The audit trail.

A verifier's question is never "what is the number" - it is "where does the
number come from". Every quantity in this package is produced as a
Calculation: an ordered list of Terms, each naming its value, unit and
provenance, ending in a result.

This is deliberately not a logging layer. The trail is the return value, so
it cannot drift out of sync with the number it explains, and it cannot be
switched off in production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator


@dataclass(frozen=True)
class Term:
    """One step in a calculation."""

    label: str
    value: float
    unit: str = ""
    detail: str = ""

    def render(self, indent: str = "") -> str:
        val = f"{self.value:,.4f}".rstrip("0").rstrip(".")
        line = f"{indent}{self.label:<42} {val:>16} {self.unit}"
        if self.detail:
            line += f"\n{indent}{'':<42} {self.detail}"
        return line.rstrip()


@dataclass
class Calculation:
    """An ordered, self-describing derivation of a single quantity."""

    name: str
    result_unit: str = ""
    terms: list[Term] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    _result: float | None = field(default=None, repr=False)

    def add(self, label: str, value: float, unit: str = "", detail: str = "") -> float:
        """Record a term and hand the value straight back, so call sites read
        as ordinary arithmetic rather than as bookkeeping."""
        self.terms.append(Term(label, value, unit, detail))
        return value

    def cite(self, source: str) -> None:
        if source not in self.citations:
            self.citations.append(source)

    def finish(self, value: float) -> float:
        self._result = value
        return value

    @property
    def result(self) -> float:
        if self._result is None:
            raise ValueError(f"calculation {self.name!r} was never finished")
        return self._result

    def __iter__(self) -> Iterator[Term]:
        return iter(self.terms)

    def render(self, indent: str = "") -> str:
        lines = [f"{indent}{self.name}", f"{indent}{'-' * len(self.name)}"]
        lines += [t.render(indent) for t in self.terms]
        if self._result is not None:
            val = f"{self._result:,.4f}".rstrip("0").rstrip(".")
            lines.append(f"{indent}{'=' * 42} {val:>16} {self.result_unit}")
        for c in self.citations:
            lines.append(f"{indent}  source: {c}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "result": self._result,
            "unit": self.result_unit,
            "terms": [
                {"label": t.label, "value": t.value, "unit": t.unit, "detail": t.detail}
                for t in self.terms
            ],
            "citations": list(self.citations),
        }
