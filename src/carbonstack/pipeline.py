"""The batch run: monitoring in, vintages out.

This is the job that has to cost almost nothing per hectare. Everything it
does is bulk: one pass over the plots per revisit date, one insert batch, one
quantification per vintage. There is no per-plot human step anywhere in it,
because model/carbon_model.py leaves about $2.53 a year to monitor a cropland
hectare and a single phone call spends more than that.

It is also re-runnable. Providers backfill, cloud clears late, a boundary gets
corrected -- so a run over a window that has already been processed must be a
no-op rather than a duplicate, which the observation uniqueness key handles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .domain import Observation, Project
from .ledger import Vintage, record_vintage
from .methodology.base import Methodology
from .remote_sensing import Provider, reconcile
from .store.repo import Store

#: What each track needs monitored. Adding a pathway means adding a row.
TRACK_VARIABLES: dict[str, tuple[str, ...]] = {
    "arr": ("canopy_height_m", "stocking_index"),
    "agroforestry": ("canopy_height_m", "stocking_index"),
    "cropland": ("practice_adopted",),
    "rice": ("practice_adopted",),
}


@dataclass
class RunReport:
    """What one batch run did, in the terms an operator cares about."""

    project_id: str
    window_start: date
    window_end: date
    plots: int = 0
    retrievals: int = 0
    stored: int = 0
    gaps: int = 0
    conflicts: list[str] = field(default_factory=list)
    variables: tuple[str, ...] = ()

    @property
    def coverage(self) -> float:
        attempts = self.retrievals + self.gaps
        return self.retrievals / attempts if attempts else 0.0

    def render(self) -> str:
        lines = [
            f"batch run — {self.project_id}",
            f"  window            {self.window_start} to {self.window_end}",
            f"  plots             {self.plots:,}",
            f"  variables         {', '.join(self.variables) or '—'}",
            f"  retrievals        {self.retrievals:,}",
            f"  new observations  {self.stored:,}"
            f"   ({self.retrievals - self.stored:,} already held)",
            f"  gaps              {self.gaps:,}   ({self.coverage:.0%} coverage)",
        ]
        for c in self.conflicts:
            lines.append(f"  ! {c}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "plots": self.plots, "retrievals": self.retrievals,
            "stored": self.stored, "gaps": self.gaps,
            "coverage": round(self.coverage, 4),
            "conflicts": list(self.conflicts),
            "variables": list(self.variables),
        }


def monitor(store: Store, project_id: str, provider: Provider, *,
            start: date, end: date, step_days: int = 5,
            ground_truth: Provider | None = None,
            variables: tuple[str, ...] | None = None,
            actor: str | None = None) -> RunReport:
    """Pull monitoring for every plot across a window and store it.

    When a ground-truth provider is supplied, each retrieval is reconciled
    against it. A disagreement wider than the combined error bar is reported
    as a conflict rather than averaged away -- that gap means the model is
    wrong for that plot, and quietly taking either number is where an
    over-crediting story starts.
    """
    project = store.load_project(project_id)
    meta = store.project_meta(project_id)
    vars_ = variables or TRACK_VARIABLES.get(meta["track"], ("stocking_index",))

    report = RunReport(project_id=project_id, window_start=start,
                       window_end=end, plots=len(project.plots), variables=vars_)
    batch: list[Observation] = []

    day = start
    while day <= end:
        for plot in project.plots.values():
            for variable in vars_:
                hit = provider.retrieve(plot, variable, day)
                truth = ground_truth.retrieve(plot, variable, day) if ground_truth else None
                chosen, warning = reconcile(hit, truth)
                if warning:
                    report.conflicts.append(warning)
                if chosen is None:
                    report.gaps += 1
                    continue
                report.retrievals += 1
                batch.append(Observation(
                    plot_id=plot.id, observed_on=chosen.observed_on,
                    variable=chosen.variable, value=chosen.value,
                    unit=chosen.unit, source=chosen.source,
                    uncertainty=chosen.uncertainty))
        day += timedelta(days=step_days)

    report.stored = store.add_observations(batch)
    store.record("pipeline.run", "project", project_id, report.to_dict(), actor=actor)
    return report


def quantify(store: Store, project_id: str, methodology: Methodology,
             provider: Provider, year: int, *,
             actor: str | None = None,
             extra_warnings: list[str] | None = None) -> Vintage:
    """Run the engine for one vintage and record the result as a draft.

    `extra_warnings` carries findings the methodology cannot see for itself --
    a season the feed knows was never dried, a management event in the window.
    They reach the vintage because approval refuses to proceed past a warning
    without a written reason, which is the only thing that makes them matter.
    """
    project = store.load_project(project_id)
    result = methodology.quantify(project, provider, year)
    for w in extra_warnings or []:
        if w not in result.warnings:
            result.warnings.append(w)
    return record_vintage(store, result, actor=actor)


def health(store: Store, project_id: str) -> dict:
    """A quick read on whether a project is actually being monitored.

    The failure mode this catches is silent: a provider changes, a credential
    expires, a job stops running, and nobody notices until a verification is
    due and the data has a six-month hole in it.
    """
    project = store.load_project(project_id)
    issues = project.eligibility_issues()
    latest = store.latest_observation_date(project_id)
    stale_days = (date.today() - latest).days if latest else None

    return {
        "project_id": project_id,
        "plots": len(project.plots),
        "area_ha": round(project.area_ha, 3),
        "creditable_ha": round(project.creditable_area_ha(), 3),
        "blocked_plots": len(issues),
        "area_blocked_pct": round(
            100 * (1 - project.creditable_area_ha() / project.area_ha), 1)
        if project.area_ha else 0.0,
        "observations": store.observation_count(project_id),
        "latest_observation": latest.isoformat() if latest else None,
        "days_since_observation": stale_days,
        "monitoring_stale": stale_days is not None and stale_days > 30,
        "never_monitored": latest is None,
    }
