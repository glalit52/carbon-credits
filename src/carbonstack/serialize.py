"""Projects to and from JSON.

Enrolment data arrives from a field app and leaves for a verifier, so the
on-disk form is a plain, readable document rather than a pickle or a database
dump. A verification body should be able to open it in a text editor and
recognise everything in it.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .domain import (
    CarbonRights, Enrollment, Farmer, Observation, Plot, Project,
    RiceEcosystem, StakeholderConsultation, TenureBasis, TrackKind,
    WaterControl,
)


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _s(value: date | None) -> str | None:
    return value.isoformat() if value else None


def to_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "track": project.track.value,
        "country": project.country,
        "start_date": _s(project.start_date),
        "crediting_period_yrs": project.crediting_period_yrs,
        "methodology_version": project.methodology_version,
        "consultation": (
            {"held_on": _s(project.consultation.held_on),
             "record_reference": project.consultation.record_reference,
             "participants": project.consultation.participants,
             "grievance_channel": project.consultation.grievance_channel}
            if project.consultation else None),
        "farmers": [
            {"id": f.id, "name": f.name, "village": f.village,
             "district": f.district, "state": f.state,
             "consent_on": _s(f.consent_on),
             "consent_reference": f.consent_reference,
             "carbon_rights": (
                 {"agreement_reference": f.carbon_rights.agreement_reference,
                  "signed_on": _s(f.carbon_rights.signed_on),
                  "holder": f.carbon_rights.holder,
                  "reversal_clause_ack": f.carbon_rights.reversal_clause_ack,
                  "expires_on": _s(f.carbon_rights.expires_on)}
                 if f.carbon_rights else None)}
            for f in project.farmers.values()
        ],
        "plots": [
            {"id": p.id, "farmer_id": p.farmer_id,
             "boundary": [list(v) for v in p.boundary],
             "tenure": p.tenure.value,
             "tenure_reference": p.tenure_reference,
             "surveyed_on": _s(p.surveyed_on),
             "area_ha": round(p.area_ha, 4),
             "fingerprint": p.fingerprint}
            for p in project.plots.values()
        ],
        "enrollments": [
            {"plot_id": e.plot_id, "project_id": e.project_id,
             "enrolled_on": _s(e.enrolled_on), "practice": e.practice,
             "species": e.species, "stems_planted": e.stems_planted,
             "baseline_captured_on": _s(e.baseline_captured_on),
             "practice_started_on": _s(e.practice_started_on),
             "ecosystem": e.ecosystem.value if e.ecosystem else None,
             "water_control": e.water_control.value if e.water_control else None}
            for e in project.enrollments
        ],
        "observations": [
            {"plot_id": o.plot_id, "observed_on": _s(o.observed_on),
             "variable": o.variable, "value": o.value, "unit": o.unit,
             "source": o.source, "uncertainty": o.uncertainty}
            for o in project.observations
        ],
    }


def from_dict(payload: dict) -> Project:
    project = Project(
        id=payload["id"],
        name=payload["name"],
        track=TrackKind(payload["track"]),
        country=payload["country"],
        start_date=_d(payload["start_date"]),
        crediting_period_yrs=payload.get("crediting_period_yrs", 30),
        methodology_version=payload.get("methodology_version", ""),
        consultation=(
            StakeholderConsultation(
                held_on=_d(payload["consultation"]["held_on"]),
                record_reference=payload["consultation"]["record_reference"],
                participants=payload["consultation"]["participants"],
                grievance_channel=payload["consultation"]["grievance_channel"])
            if payload.get("consultation") else None),
    )
    for f in payload.get("farmers", []):
        cr = f.get("carbon_rights")
        project.add_farmer(Farmer(
            id=f["id"], name=f["name"], village=f["village"],
            district=f["district"], state=f["state"],
            consent_on=_d(f.get("consent_on")),
            consent_reference=f.get("consent_reference", ""),
            carbon_rights=(CarbonRights(
                agreement_reference=cr["agreement_reference"],
                signed_on=_d(cr["signed_on"]), holder=cr["holder"],
                reversal_clause_ack=cr.get("reversal_clause_ack", False),
                expires_on=_d(cr.get("expires_on"))) if cr else None),
        ))
    for p in payload.get("plots", []):
        project.add_plot(Plot(
            id=p["id"], farmer_id=p["farmer_id"],
            boundary=[tuple(v) for v in p["boundary"]],
            tenure=TenureBasis(p["tenure"]),
            tenure_reference=p.get("tenure_reference", ""),
            surveyed_on=_d(p.get("surveyed_on")),
        ))
    for e in payload.get("enrollments", []):
        project.enroll(Enrollment(
            plot_id=e["plot_id"], project_id=e["project_id"],
            enrolled_on=_d(e["enrolled_on"]), practice=e["practice"],
            species=e.get("species", []), stems_planted=e.get("stems_planted"),
            baseline_captured_on=_d(e.get("baseline_captured_on")),
            practice_started_on=_d(e.get("practice_started_on")),
            ecosystem=(RiceEcosystem(e["ecosystem"]) if e.get("ecosystem") else None),
            water_control=(WaterControl(e["water_control"])
                           if e.get("water_control") else None),
        ))
    for o in payload.get("observations", []):
        project.observe(Observation(
            plot_id=o["plot_id"], observed_on=_d(o["observed_on"]),
            variable=o["variable"], value=o["value"], unit=o["unit"],
            source=o["source"], uncertainty=o.get("uncertainty"),
        ))
    return project


def save(project: Project, path: str | Path) -> None:
    Path(path).write_text(json.dumps(to_dict(project), indent=2) + "\n")


def load(path: str | Path) -> Project:
    return from_dict(json.loads(Path(path).read_text()))
