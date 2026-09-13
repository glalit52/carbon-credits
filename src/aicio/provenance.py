"""Where every number came from.

The PRD's hardest requirement is not a calculation, it is a property: every
material fact retains source, timestamp, provider, transformation and
confidence, so the AI can say where information came from and so a stale price
can be recognised as stale rather than quietly believed.

That is enforced here by making the carrier of a value and the carrier of its
history the same object. A :class:`Fact` cannot be constructed without a
:class:`Provenance`, so there is no path by which an ungrounded number reaches
the model or the user. This is the same idea as carbonstack's Calculation --
the trail is the return value, not a log line -- applied to market data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable


class SourceKind(str, Enum):
    """How much weight a fact's origin deserves.

    Ordered from most to least authoritative. The decision engine refuses to
    act on ``MODEL`` or ``ASSUMPTION`` facts alone: an assumption may shape a
    projection, never a BUY.
    """

    USER_UPLOAD = "user_upload"        # a statement the user gave us
    USER_INPUT = "user_input"          # typed by the user
    CONNECTED_ACCOUNT = "connected_account"   # broker / aggregator API
    MARKET_DATA = "market_data"        # licensed price or NAV feed
    REFERENCE_DATA = "reference_data"  # fund master, sector maps, benchmarks
    DERIVED = "derived"                # computed by aicio.engine from the above
    RESEARCH = "research"              # third-party commentary; never a fact
    MODEL = "model"                    # LLM output
    ASSUMPTION = "assumption"          # explicit, user-visible assumption


#: Facts that may be presented as fact rather than as opinion or assumption.
AUTHORITATIVE = {
    SourceKind.USER_UPLOAD,
    SourceKind.USER_INPUT,
    SourceKind.CONNECTED_ACCOUNT,
    SourceKind.MARKET_DATA,
    SourceKind.REFERENCE_DATA,
    SourceKind.DERIVED,
}

#: How long each kind of fact stays usable before it must be refreshed or
#: flagged. Beyond this a recommendation built on it is suspect, so the engine
#: downgrades confidence and the banker says so out loud.
FRESHNESS: dict[SourceKind, timedelta] = {
    SourceKind.MARKET_DATA: timedelta(days=4),      # allows a long weekend
    SourceKind.REFERENCE_DATA: timedelta(days=45),
    SourceKind.CONNECTED_ACCOUNT: timedelta(days=7),
    SourceKind.USER_UPLOAD: timedelta(days=120),
    SourceKind.USER_INPUT: timedelta(days=400),
    SourceKind.DERIVED: timedelta(days=4),
    SourceKind.RESEARCH: timedelta(days=30),
    SourceKind.MODEL: timedelta(days=1),
    SourceKind.ASSUMPTION: timedelta(days=400),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Provenance:
    """The history of a single value."""

    kind: SourceKind
    provider: str                       # "AMFI", "user:cas_upload", "engine.returns"
    observed_at: datetime               # when the source produced it
    reference: str = ""                 # file name, URL, folio, statement page
    transformation: str = ""            # what we did to it after receiving it
    confidence: float = 1.0             # 0..1, the source's own reliability
    inputs: tuple[str, ...] = ()        # fact ids this was derived from

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence out of range: {self.confidence}")
        if self.observed_at.tzinfo is None:
            object.__setattr__(self, "observed_at", self.observed_at.replace(tzinfo=timezone.utc))

    def age(self, *, now: datetime | None = None) -> timedelta:
        return (now or utcnow()) - self.observed_at

    def is_stale(self, *, now: datetime | None = None) -> bool:
        return self.age(now=now) > FRESHNESS[self.kind]

    def staleness_penalty(self, *, now: datetime | None = None) -> float:
        """Multiplier applied to confidence as a fact ages.

        Decays linearly from 1.0 at the freshness limit to 0.2 at four times
        it. Old data is not worthless -- a six-month-old fund factsheet still
        says something -- but it must not carry the same weight as today's.
        """
        limit = FRESHNESS[self.kind]
        age = self.age(now=now)
        if age <= limit:
            return 1.0
        overshoot = (age - limit) / (limit * 3)
        return max(0.2, 1.0 - 0.8 * min(1.0, overshoot))

    def derive(self, provider: str, transformation: str, inputs: Iterable[str] = ()) -> "Provenance":
        """Produce the provenance of something computed from this one."""
        return replace(
            self,
            kind=SourceKind.DERIVED,
            provider=provider,
            transformation=transformation,
            inputs=tuple(inputs),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "provider": self.provider,
            "observed_at": self.observed_at.isoformat(),
            "reference": self.reference,
            "transformation": self.transformation,
            "confidence": round(self.confidence, 4),
            "inputs": list(self.inputs),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Provenance":
        return cls(
            kind=SourceKind(raw["kind"]),
            provider=raw["provider"],
            observed_at=datetime.fromisoformat(raw["observed_at"]),
            reference=raw.get("reference", ""),
            transformation=raw.get("transformation", ""),
            confidence=float(raw.get("confidence", 1.0)),
            inputs=tuple(raw.get("inputs", ())),
        )


def user_input(reference: str = "", *, at: datetime | None = None) -> Provenance:
    return Provenance(SourceKind.USER_INPUT, "user", at or utcnow(), reference)


def assumption(label: str, *, at: datetime | None = None) -> Provenance:
    return Provenance(SourceKind.ASSUMPTION, "aicio", at or utcnow(), label, confidence=0.6)


@dataclass(frozen=True)
class Fact:
    """A value the system is prepared to defend.

    ``id`` is content-addressed so the same fact computed twice is the same
    fact, which is what makes a recommendation reproducible from a stored
    input snapshot -- the Definition of Done in the PRD's engineering plan.
    """

    name: str
    value: Any
    unit: str
    provenance: Provenance
    detail: str = ""

    @property
    def id(self) -> str:
        payload = json.dumps(
            {
                "name": self.name,
                "value": _stable(self.value),
                "unit": self.unit,
                "provenance": self.provenance.to_dict(),
            },
            sort_keys=True,
            default=str,
        )
        return "f_" + hashlib.sha256(payload.encode()).hexdigest()[:16]

    @property
    def authoritative(self) -> bool:
        return self.provenance.kind in AUTHORITATIVE

    def confidence(self, *, now: datetime | None = None) -> float:
        return self.provenance.confidence * self.provenance.staleness_penalty(now=now)

    def is_stale(self, *, now: datetime | None = None) -> bool:
        return self.provenance.is_stale(now=now)

    def render(self) -> str:
        value = self.value
        if isinstance(value, float):
            value = f"{value:,.4f}".rstrip("0").rstrip(".")
        tail = f" ({self.detail})" if self.detail else ""
        return f"{self.name}: {value} {self.unit}{tail}".strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "value": _stable(self.value),
            "unit": self.unit,
            "detail": self.detail,
            "stale": self.is_stale(),
            "confidence": round(self.confidence(), 4),
            "provenance": self.provenance.to_dict(),
        }


def _stable(value: Any) -> Any:
    """Round floats before hashing so that arithmetic noise does not change a
    fact's identity while its meaning stays the same."""
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, dict):
        return {k: _stable(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_stable(v) for v in value]
    return value


@dataclass
class FactSheet:
    """The grounded context handed to the AI layer.

    Nothing else is: the banker sees this object and the user's question, and
    is told in its system prompt that anything not in here does not exist.
    """

    subject: str
    facts: list[Fact] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, fact: Fact) -> Fact:
        self.facts.append(fact)
        return fact

    def record(self, name: str, value: Any, unit: str, provenance: Provenance, detail: str = "") -> Fact:
        return self.add(Fact(name, value, unit, provenance, detail))

    def note(self, text: str) -> None:
        """A limitation worth saying out loud -- missing data, a conflict, an
        assumption the user should be able to challenge."""
        self.notes.append(text)

    def get(self, name: str) -> Fact | None:
        for fact in self.facts:
            if fact.name == name:
                return fact
        return None

    def value(self, name: str, default: Any = None) -> Any:
        fact = self.get(name)
        return default if fact is None else fact.value

    @property
    def ids(self) -> list[str]:
        return [fact.id for fact in self.facts]

    def stale(self, *, now: datetime | None = None) -> list[Fact]:
        return [f for f in self.facts if f.is_stale(now=now)]

    def weakest_confidence(self, *, now: datetime | None = None) -> float:
        if not self.facts:
            return 0.0
        return min(f.confidence(now=now) for f in self.facts)

    def merge(self, other: "FactSheet") -> "FactSheet":
        self.facts.extend(other.facts)
        self.notes.extend(other.notes)
        return self

    def render(self) -> str:
        lines = [f"# {self.subject}"]
        lines += [f"- {f.render()}   [{f.id} · {f.provenance.provider}]" for f in self.facts]
        if self.notes:
            lines.append("# Limitations")
            lines += [f"- {n}" for n in self.notes]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "facts": [f.to_dict() for f in self.facts],
            "notes": list(self.notes),
        }
