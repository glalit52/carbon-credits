"""Field sensors: the ground truth the radar is scored against.

The SAR detector's 96% accuracy is against a simulation, and the README says
so: real validation needs water-level loggers in a sample of paddies, which is
what VM0051 expects to see and what that number stands in for. SenseGrass
already runs field hardware, which is the asset neither Mitti Labs nor Varaha
had to begin with -- this module is where it plugs in.

A logger in a perforated AWD field tube reports the water level relative to
the soil surface: positive is ponded water, negative is the water table below
the surface. Three things go wrong with that stream often enough that the
ingest checks every one before a reading is allowed near a detector score:

* **Gaps.** Batteries die in week six of a season, and a day with no reading
  is not a dry day.
* **Flatlines.** A tube silted at the bottom reports the same level for a
  fortnight while the field around it floods and drains. An unchanging
  reading over days in a field that is being irrigated is a fault, not a
  measurement.
* **Spikes.** A frog, a farmer's hand, a dislodged sensor. A level that jumps
  further in an hour than a paddy can physically fill or drain is dropped.

Days are classified with a dead band between the two states. Water a
centimetre below the surface is neither the mirror a flooded field presents
to the radar nor a drained field, and scoring the detector against a coin
toss would only measure the coin.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from ..sar import Classification, WaterState, score

FLOODED_ABOVE_CM = 2.0
"""Ponded water at least this deep reads as flooded to C-band SAR."""

DRAINED_BELOW_CM = -5.0
"""Water table at least this far below the surface: no standing water."""

SAFE_AWD_THRESHOLD_CM = -15.0
"""The IRRI 'safe AWD' re-flooding trigger. A dry-down that reaches it is the
practice the methane reduction is credited for; one that does not is a field
that briefly lost its ponding."""

MAX_RATE_CM_PER_H = 6.0
"""Faster than a paddy fills from a canal or drains through a bund. A step
larger than this between consecutive readings is a disturbance."""

FLATLINE_HOURS = 72
"""A level unchanged to the millimetre for this long is a stuck sensor."""

MIN_READINGS_PER_DAY = 4


@dataclass(frozen=True)
class Reading:
    device_id: str
    plot_id: str
    at: datetime
    water_level_cm: float


@dataclass
class DayState:
    day: date
    mean_cm: float
    min_cm: float
    readings: int
    state: WaterState

    @property
    def flooded(self) -> bool | None:
        if self.state is WaterState.AMBIGUOUS:
            return None
        return self.state is WaterState.FLOODED


@dataclass
class LoggerRecord:
    """One device's cleaned record, and everything that was removed from it."""

    device_id: str
    plot_id: str
    days: list[DayState]
    dropped_spikes: int = 0
    flatline_hours: float = 0.0
    gap_days: list[date] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def truth(self) -> dict[date, bool]:
        """Days with a clear state, as the detector's score expects."""
        return {d.day: d.flooded for d in self.days if d.flooded is not None}

    def dry_downs(self, threshold_cm: float = SAFE_AWD_THRESHOLD_CM) -> list[tuple[date, date, float]]:
        """Measured AWD events: from losing ponding to re-flooding.

        Only spells whose deepest point reaches `threshold_cm` count -- the
        same rule the methodology applies to the practice, applied here to
        the measurement instead of the claim.
        """
        events = []
        start = None
        deepest = 0.0
        for d in self.days:
            if d.state is WaterState.DRAINED or (start is not None and d.state is WaterState.AMBIGUOUS):
                if start is None:
                    start, deepest = d.day, d.min_cm
                deepest = min(deepest, d.min_cm)
            elif d.state is WaterState.FLOODED and start is not None:
                if deepest <= threshold_cm:
                    events.append((start, d.day, deepest))
                start = None
        if start is not None and deepest <= threshold_cm:
            events.append((start, self.days[-1].day, deepest))
        return events

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id, "plot_id": self.plot_id,
            "days": len(self.days),
            "clear_days": len(self.truth()),
            "dropped_spikes": self.dropped_spikes,
            "flatline_hours": round(self.flatline_hours, 1),
            "gap_days": [d.isoformat() for d in self.gap_days],
            "dry_downs": [
                {"from": a.isoformat(), "to": b.isoformat(), "deepest_cm": round(c, 1)}
                for a, b, c in self.dry_downs()
            ],
            "issues": self.issues,
        }


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def _ts(text: str) -> datetime:
    dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_csv(text: str) -> list[Reading]:
    """`device_id,plot_id,timestamp,water_level_cm`, header required."""
    rows = list(csv.DictReader(io.StringIO(text)))
    need = {"device_id", "plot_id", "timestamp", "water_level_cm"}
    if rows and not need <= set(rows[0]):
        raise ValueError(f"sensor CSV needs columns {sorted(need)}")
    out = []
    for i, r in enumerate(rows, start=2):
        level = (r["water_level_cm"] or "").strip()
        if not level:
            continue
        try:
            out.append(Reading(r["device_id"].strip(), r["plot_id"].strip(),
                               _ts(r["timestamp"]), float(level)))
        except ValueError as exc:
            raise ValueError(f"sensor CSV line {i}: {exc}") from exc
    return out


def parse_json(text: str) -> list[Reading]:
    """A webhook batch: `{"device_id", "plot_id", "readings": [{"t", "level_cm"}]}`
    or a list of such batches. This is the shape a gateway posts."""
    data = json.loads(text)
    batches = data if isinstance(data, list) else [data]
    out = []
    for b in batches:
        for r in b.get("readings", []):
            if r.get("level_cm") is None:
                continue
            out.append(Reading(b["device_id"], b["plot_id"], _ts(r["t"]),
                               float(r["level_cm"])))
    return out


def classify_level(mean_cm: float) -> WaterState:
    if mean_cm >= FLOODED_ABOVE_CM:
        return WaterState.FLOODED
    if mean_cm <= DRAINED_BELOW_CM:
        return WaterState.DRAINED
    return WaterState.AMBIGUOUS


def clean(readings: list[Reading]) -> list[LoggerRecord]:
    """Group by device, drop faults, and reduce to one state per day."""
    by_device: dict[str, list[Reading]] = defaultdict(list)
    for r in readings:
        by_device[r.device_id].append(r)

    records = []
    for device, rs in sorted(by_device.items()):
        rs.sort(key=lambda r: r.at)
        plots = {r.plot_id for r in rs}
        rec = LoggerRecord(device, rs[0].plot_id, [])
        if len(plots) > 1:
            rec.issues.append(
                f"device reported for {len(plots)} plots ({', '.join(sorted(plots))}); "
                f"a moved logger needs a new device record")

        # Spikes: a step faster than water can move.
        kept: list[Reading] = []
        for r in rs:
            if kept:
                hours = max((r.at - kept[-1].at).total_seconds() / 3600, 1 / 60)
                if abs(r.water_level_cm - kept[-1].water_level_cm) / hours > MAX_RATE_CM_PER_H \
                        and hours < 6:
                    rec.dropped_spikes += 1
                    continue
            kept.append(r)

        # Flatlines: drop runs of identical readings longer than the limit.
        flat: set[int] = set()
        i = 0
        while i < len(kept):
            j = i
            while j + 1 < len(kept) and math.isclose(
                    kept[j + 1].water_level_cm, kept[i].water_level_cm, abs_tol=0.05):
                j += 1
            span = (kept[j].at - kept[i].at).total_seconds() / 3600
            if span >= FLATLINE_HOURS:
                flat.update(range(i, j + 1))
                rec.flatline_hours += span
            i = j + 1
        if rec.flatline_hours:
            rec.issues.append(
                f"{rec.flatline_hours:.0f} h of unchanging readings removed; "
                f"check the tube for silting")
        good = [r for k, r in enumerate(kept) if k not in flat]

        by_day: dict[date, list[float]] = defaultdict(list)
        for r in good:
            by_day[r.at.date()].append(r.water_level_cm)
        if not by_day:
            rec.issues.append("no usable readings")
            records.append(rec)
            continue
        first, last = min(by_day), max(by_day)
        d = first
        while d <= last:
            vals = by_day.get(d, [])
            if len(vals) < MIN_READINGS_PER_DAY:
                rec.gap_days.append(d)
            else:
                mean = sum(vals) / len(vals)
                rec.days.append(DayState(d, mean, min(vals), len(vals),
                                         classify_level(mean)))
            d += timedelta(days=1)
        span_days = (last - first).days + 1
        if rec.gap_days and len(rec.gap_days) / span_days > 0.2:
            rec.issues.append(
                f"{len(rec.gap_days)} of {span_days} days missing or thin; "
                f"the record cannot support a season-level claim")
        records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Validation of the radar against the loggers
# ---------------------------------------------------------------------------

@dataclass
class DetectorValidation:
    """The detector scored against measured water, not simulated water."""

    plot_id: str
    devices: list[str]
    matched_passes: int
    result: dict
    unmatched_passes: int

    @property
    def over_credit_errors(self) -> int:
        """Passes called drained while the logger saw standing water."""
        return self.result.get("false_negative", 0)

    @property
    def sufficient(self) -> bool:
        """Enough matched passes for the accuracy to mean something.

        Thirty is the floor below which a single wrong call moves accuracy by
        more than three points -- the same order as the claim being tested.
        """
        return self.matched_passes >= 30

    def to_dict(self) -> dict:
        return {"plot_id": self.plot_id, "devices": self.devices,
                "matched_passes": self.matched_passes,
                "unmatched_passes": self.unmatched_passes,
                "sufficient": self.sufficient,
                "over_credit_errors": self.over_credit_errors,
                **self.result}


def validate_detector(calls: list[Classification],
                      records: list[LoggerRecord]) -> DetectorValidation:
    """Score radar calls on one plot against every logger on that plot.

    Where two loggers disagree about a day, the day is dropped: a plot that
    is half flooded is a plot the radar cannot be wrong about.
    """
    if not records:
        raise ValueError("no logger records to validate against")
    plot = records[0].plot_id
    votes: dict[date, set[bool]] = defaultdict(set)
    for rec in records:
        for d, flooded in rec.truth().items():
            votes[d].add(flooded)
    truth = {d: next(iter(v)) for d, v in votes.items() if len(v) == 1}
    matched = [c for c in calls if c.day in truth]
    return DetectorValidation(
        plot_id=plot,
        devices=[r.device_id for r in records],
        matched_passes=len(matched),
        result=score(matched, truth),
        unmatched_passes=len(calls) - len(matched),
    )
