"""The store: reads, writes, and the event chain that makes them auditable.

Two things here are not ordinary CRUD and are the point of the module.

First, **every state change writes an event**, and the events form a hash
chain: each event's hash covers its own content and its predecessor's hash. A
row edited behind the application's back breaks the chain, and `verify_chain`
finds where. This is cheap to build and it is the difference between "our
database says so" and something a verifier can test.

Second, **nothing here silently overwrites a quantification**. Re-quantifying
a vintage that has been issued is refused, because the issued number is a
commercial fact and a recomputation that disagrees with it is an incident, not
an update.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..domain import (
    Enrollment, Farmer, Observation, Plot, Project, TenureBasis, TrackKind,
)
from .schema import migrate

GENESIS = "0" * 64


class StoreError(RuntimeError):
    """A refused operation. The message says what rule was broken."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _s(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _canonical(payload: Any) -> str:
    """Stable JSON, so a hash over it is reproducible anywhere."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


class Store:
    """A carbon project database."""

    def __init__(self, path: str | Path = ":memory:", *, actor: str = "system"):
        self.path = str(path)
        self.actor = actor
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        migrate(self.conn)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # -- events -------------------------------------------------------------

    def record(self, kind: str, subject_type: str, subject_id: str,
               payload: dict | None = None, *, actor: str | None = None) -> str:
        """Append an event and return its hash.

        Called by every mutating method here. Callers may also call it directly
        for things that happen outside the store -- a verifier visit, a
        registry submission -- so the chain stays the single narrative of the
        project.
        """
        row = self.conn.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else GENESIS
        at = _now()
        body = {
            "at": at, "actor": actor or self.actor, "kind": kind,
            "subject_type": subject_type, "subject_id": subject_id,
            "payload": payload or {}, "prev_hash": prev,
        }
        digest = hashlib.sha256(_canonical(body).encode()).hexdigest()
        self.conn.execute(
            "INSERT INTO events (at, actor, kind, subject_type, subject_id,"
            " payload_json, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?)",
            (at, body["actor"], kind, subject_type, subject_id,
             _canonical(payload or {}), prev, digest),
        )
        return digest

    def events(self, subject_type: str | None = None,
               subject_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM events"
        args: list[Any] = []
        if subject_type:
            sql += " WHERE subject_type = ?"
            args.append(subject_type)
            if subject_id:
                sql += " AND subject_id = ?"
                args.append(subject_id)
        sql += " ORDER BY id"
        return [
            {**dict(r), "payload": json.loads(r["payload_json"])}
            for r in self.conn.execute(sql, args)
        ]

    def verify_chain(self) -> tuple[bool, str | None]:
        """Recompute every event hash. Returns (intact, first bad event id).

        A verifier runs this. So should a nightly job -- the value of a
        tamper-evident log is only realised if somebody actually checks it.
        """
        prev = GENESIS
        for r in self.conn.execute("SELECT * FROM events ORDER BY id"):
            body = {
                "at": r["at"], "actor": r["actor"], "kind": r["kind"],
                "subject_type": r["subject_type"], "subject_id": r["subject_id"],
                "payload": json.loads(r["payload_json"]), "prev_hash": prev,
            }
            expected = hashlib.sha256(_canonical(body).encode()).hexdigest()
            if r["prev_hash"] != prev or r["hash"] != expected:
                return False, str(r["id"])
            prev = r["hash"]
        return True, None

    # -- projects -----------------------------------------------------------

    def save_project(self, project: Project, *, methodology_id: str,
                     registry: str = "", registry_ref: str = "") -> None:
        """Write a project and everything under it. Idempotent by id."""
        with self.tx() as conn:
            existing = conn.execute(
                "SELECT id FROM projects WHERE id = ?", (project.id,)).fetchone()
            conn.execute(
                "INSERT OR REPLACE INTO projects (id, name, track, country,"
                " start_date, crediting_period_yrs, methodology_id, registry,"
                " registry_ref, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (project.id, project.name, project.track.value, project.country,
                 _s(project.start_date), project.crediting_period_yrs,
                 methodology_id, registry, registry_ref, _now()),
            )
            for f in project.farmers.values():
                conn.execute(
                    "INSERT OR REPLACE INTO farmers (id, project_id, name, village,"
                    " district, state, consent_on, consent_reference, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (f.id, project.id, f.name, f.village, f.district, f.state,
                     _s(f.consent_on), f.consent_reference, _now()),
                )
            for p in project.plots.values():
                conn.execute(
                    "INSERT OR REPLACE INTO plots (id, project_id, farmer_id,"
                    " boundary_json, tenure, tenure_reference, surveyed_on,"
                    " area_ha, fingerprint, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (p.id, project.id, p.farmer_id, _canonical([list(v) for v in p.boundary]),
                     p.tenure.value, p.tenure_reference, _s(p.surveyed_on),
                     p.area_ha, p.fingerprint, _now()),
                )
            for e in project.enrollments:
                conn.execute(
                    "INSERT OR IGNORE INTO enrollments (project_id, plot_id,"
                    " enrolled_on, practice, species_json, stems_planted, created_at)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (project.id, e.plot_id, _s(e.enrolled_on), e.practice,
                     _canonical(e.species), e.stems_planted, _now()),
                )
            self.record("project.saved" if existing is None else "project.updated",
                        "project", project.id,
                        {"plots": len(project.plots),
                         "farmers": len(project.farmers),
                         "area_ha": round(project.area_ha, 4),
                         "methodology": methodology_id})

    def load_project(self, project_id: str) -> Project:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise StoreError(f"no project {project_id!r}")

        project = Project(
            id=row["id"], name=row["name"], track=TrackKind(row["track"]),
            country=row["country"], start_date=_d(row["start_date"]),
            crediting_period_yrs=row["crediting_period_yrs"],
        )
        for r in self.conn.execute(
                "SELECT * FROM farmers WHERE project_id = ? ORDER BY id", (project_id,)):
            project.add_farmer(Farmer(
                id=r["id"], name=r["name"], village=r["village"],
                district=r["district"], state=r["state"],
                consent_on=_d(r["consent_on"]),
                consent_reference=r["consent_reference"]))
        for r in self.conn.execute(
                "SELECT * FROM plots WHERE project_id = ? ORDER BY id", (project_id,)):
            project.add_plot(Plot(
                id=r["id"], farmer_id=r["farmer_id"],
                boundary=[tuple(v) for v in json.loads(r["boundary_json"])],
                tenure=TenureBasis(r["tenure"]),
                tenure_reference=r["tenure_reference"],
                surveyed_on=_d(r["surveyed_on"])))
        for r in self.conn.execute(
                "SELECT * FROM enrollments WHERE project_id = ? ORDER BY id", (project_id,)):
            project.enroll(Enrollment(
                plot_id=r["plot_id"], project_id=project_id,
                enrolled_on=_d(r["enrolled_on"]), practice=r["practice"],
                species=json.loads(r["species_json"]),
                stems_planted=r["stems_planted"]))
        for r in self.conn.execute(
                "SELECT o.* FROM observations o JOIN plots p ON p.id = o.plot_id"
                " WHERE p.project_id = ? ORDER BY o.observed_on", (project_id,)):
            project.observe(Observation(
                plot_id=r["plot_id"], observed_on=_d(r["observed_on"]),
                variable=r["variable"], value=r["value"], unit=r["unit"],
                source=r["source"], uncertainty=r["uncertainty"]))
        return project

    def project_meta(self, project_id: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise StoreError(f"no project {project_id!r}")
        return dict(row)

    def list_projects(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT p.*, "
            " (SELECT COUNT(*) FROM plots WHERE project_id = p.id) AS plot_count,"
            " (SELECT COALESCE(SUM(area_ha),0) FROM plots WHERE project_id = p.id) AS area_ha"
            " FROM projects p ORDER BY p.id")]

    # -- observations -------------------------------------------------------

    def add_observations(self, observations: list[Observation]) -> int:
        """Insert monitoring records. Re-ingesting the same pass is a no-op.

        The uniqueness key is (plot, date, variable, source), so a pipeline can
        be re-run over a window without duplicating -- which it will be, every
        time a provider backfills.
        """
        if not observations:
            return 0
        with self.tx() as conn:
            before = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            conn.executemany(
                "INSERT OR IGNORE INTO observations (plot_id, observed_on, variable,"
                " value, unit, source, uncertainty, created_at) VALUES (?,?,?,?,?,?,?,?)",
                [(o.plot_id, _s(o.observed_on), o.variable, o.value, o.unit,
                  o.source, o.uncertainty, _now()) for o in observations],
            )
            after = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            added = after - before
            if added:
                plots = sorted({o.plot_id for o in observations})
                self.record("observations.ingested", "project",
                            self._project_of_plot(plots[0]) or "unknown",
                            {"added": added, "offered": len(observations),
                             "plots": len(plots),
                             "variables": sorted({o.variable for o in observations})})
        return added

    def _project_of_plot(self, plot_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT project_id FROM plots WHERE id = ?", (plot_id,)).fetchone()
        return row["project_id"] if row else None

    def observation_count(self, project_id: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM observations o JOIN plots p ON p.id = o.plot_id"
            " WHERE p.project_id = ?", (project_id,)).fetchone()[0]

    def latest_observation_date(self, project_id: str) -> date | None:
        row = self.conn.execute(
            "SELECT MAX(observed_on) AS d FROM observations o"
            " JOIN plots p ON p.id = o.plot_id WHERE p.project_id = ?",
            (project_id,)).fetchone()
        return _d(row["d"]) if row and row["d"] else None


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
