"""A synthetic portfolio, for exercising the pipeline before real data exists.

Deliberately not clean: it contains a plot with no tenure document and a
farmer with no recorded consent, because those are the rows that decide
whether a project issues on schedule, and a demo that omits them teaches the
wrong lesson about what this system is for.
"""

from __future__ import annotations

from datetime import date

from .domain import (
    CarbonRights, Enrollment, Farmer, Plot, Project, RiceEcosystem,
    StakeholderConsultation, TenureBasis, TrackKind, WaterControl,
)


def _square(lon: float, lat: float, side_deg: float):
    return [(lon, lat), (lon + side_deg, lat),
            (lon + side_deg, lat + side_deg), (lon, lat + side_deg)]


def demo_estate(n_farmers: int = 24, planting_year: int = 2025) -> Project:
    """Track B - an agroforestry block planting in coastal Andhra Pradesh."""
    project = Project(
        id="AP-ARR-001",
        name="Krishna delta agroforestry",
        track=TrackKind.AGROFORESTRY,
        country="IN",
        start_date=date(planting_year, 7, 1),
        methodology_version="VM0047 v1.1",
        consultation=StakeholderConsultation(
            held_on=date(planting_year, 5, 20),
            record_reference="CONSULT/AP-ARR-001/001",
            participants=61,
            grievance_channel="mandal office, fortnightly; toll-free 1800-000-000"),
    )
    for i in range(n_farmers):
        # One farmer in twelve has no consent on file, one plot in eight has no
        # tenure document. Both rates are optimistic against real enrolment.
        has_consent = i % 12 != 0
        documented = i % 8 != 0
        has_rights = i % 10 != 0
        baseline_first = i % 9 != 0

        farmer = project.add_farmer(Farmer(
            id=f"F{i:03d}", name=f"Farmer {i:03d}", village="Kondapur",
            district="Krishna", state="Andhra Pradesh",
            consent_on=date(planting_year, 6, 1) if has_consent else None,
            consent_reference=f"CONSENT/{planting_year}/{i:03d}" if has_consent else "",
            carbon_rights=(CarbonRights(
                agreement_reference=f"CRA/{planting_year}/{i:03d}",
                signed_on=date(planting_year, 6, 1),
                holder="SenseGrass (project proponent)",
                reversal_clause_ack=True) if has_rights else None),
        ))
        plot = project.add_plot(Plot(
            id=f"AP-P{i:03d}", farmer_id=farmer.id,
            boundary=_square(80.90 + (i % 8) * 0.004, 16.30 + (i // 8) * 0.004, 0.0035),
            tenure=TenureBasis.OWNED_TITLE if documented else TenureBasis.UNDOCUMENTED,
            tenure_reference=f"RoR/{planting_year - 6}/{i:04d}" if documented else "",
            surveyed_on=date(planting_year, 6, 15),
        ))
        project.enroll(Enrollment(
            plot_id=plot.id, project_id=project.id,
            enrolled_on=date(planting_year, 7, 15),
            practice="block_planting",
            species=["Melia dubia", "Tectona grandis"],
            stems_planted=int(plot.area_ha * 400),
            baseline_captured_on=date(planting_year, 6, 10),
            practice_started_on=date(planting_year, 7, 15) if baseline_first
            else date(planting_year, 5, 1),
        ))
    return project


def demo_bridge(n_farmers: int = 40, first_season: int = 2025) -> Project:
    """Track A - rice water management in the same districts."""
    project = Project(
        id="AP-RICE-001",
        name="Krishna delta rice water management",
        track=TrackKind.RICE,
        country="IN",
        start_date=date(first_season, 6, 1),
        methodology_version="VM0051 v1.1",
        consultation=StakeholderConsultation(
            held_on=date(first_season, 4, 15),
            record_reference="CONSULT/AP-RICE-001/001",
            participants=88,
            grievance_channel="mandal office, fortnightly; toll-free 1800-000-000"),
    )
    for i in range(n_farmers):
        has_consent = i % 15 != 0
        has_rights = i % 13 != 0
        # A handful of fields are the wrong kind of rice for VM0051.
        ecosystem = (RiceEcosystem.RAINFED if i % 11 == 0
                     else RiceEcosystem.IRRIGATED_LOWLAND)
        control = (WaterControl.IRRIGATION_ONLY if i % 14 == 0
                   else WaterControl.FULL)
        farmer = project.add_farmer(Farmer(
            id=f"R{i:03d}", name=f"Farmer {i:03d}", village="Gudivada",
            district="Krishna", state="Andhra Pradesh",
            consent_on=date(first_season, 5, 1) if has_consent else None,
            consent_reference=f"CONSENT/{first_season}/R{i:03d}" if has_consent else "",
            carbon_rights=(CarbonRights(
                agreement_reference=f"CRA/{first_season}/R{i:03d}",
                signed_on=date(first_season, 5, 1),
                holder="SenseGrass (project proponent)",
                reversal_clause_ack=True) if has_rights else None),
        ))
        plot = project.add_plot(Plot(
            id=f"AP-R{i:03d}", farmer_id=farmer.id,
            boundary=_square(81.20 + (i % 10) * 0.005, 16.42 + (i // 10) * 0.005, 0.004),
            tenure=TenureBasis.REGISTERED_LEASE,
            tenure_reference=f"LEASE/{first_season}/{i:04d}",
            surveyed_on=date(first_season, 5, 15),
        ))
        project.enroll(Enrollment(
            plot_id=plot.id, project_id=project.id,
            enrolled_on=date(first_season, 6, 10), practice="awd",
            baseline_captured_on=date(first_season, 5, 10),
            practice_started_on=date(first_season, 6, 20),
            ecosystem=ecosystem, water_control=control,
        ))
    return project
