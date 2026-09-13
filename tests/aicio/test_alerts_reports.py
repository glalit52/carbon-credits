"""Alerts that stay quiet, and reports that say what changed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aicio.alerts import (
    AlertFeedback, PER_RUN_CAP, detect, filter_alerts, mark, snooze,
    summarise_feedback,
)
from aicio.domain import Alert, AlertStatus, Priority, User
from aicio.reports import daily_brief, monthly_committee, weekly_report
from aicio.evals.scenarios import build
from aicio.evals.suite import _run


@pytest.fixture
def user():
    return User(id="user_demo", email="d@example.com", quiet_hours=(22, 7))


def _at(hour: int) -> datetime:
    return datetime(2026, 9, 12, hour, 0, tzinfo=timezone.utc)


def test_alerts_are_generated_from_the_analysis(analysis, recommendations):
    kinds = {a.alert_type for a in detect(analysis, recommendations)}
    assert {"allocation_breach", "goal_deterioration"} <= kinds


def test_the_same_state_produces_the_same_dedupe_key(analysis, recommendations):
    first = {a.dedupe_key for a in detect(analysis, recommendations)}
    second = {a.dedupe_key for a in detect(analysis, recommendations)}
    assert first == second


def test_an_open_alert_is_not_raised_again(analysis, recommendations, user):
    candidates = detect(analysis, recommendations)
    run = filter_alerts(candidates, user=user, now=_at(10))
    again = filter_alerts(candidates, user=user, existing=run.alerts + run.digest, now=_at(11))
    assert not again.alerts
    assert all("already open" in reason for _, reason in again.suppressed)


def test_a_dismissed_alert_stays_dismissed_until_the_state_changes(
    analysis, recommendations, user
):
    candidates = detect(analysis, recommendations)
    dismissed = [mark(a, useful=False) for a in candidates]
    run = filter_alerts(candidates, user=user, existing=dismissed, now=_at(10))
    assert not run.alerts


def test_a_snoozed_alert_returns_after_the_snooze(analysis, recommendations, user):
    candidates = detect(analysis, recommendations)
    snoozed = [snooze(a, days=30, now=_at(10)) for a in candidates]
    during = filter_alerts(candidates, user=user, existing=snoozed, now=_at(12))
    after = filter_alerts(
        candidates, user=user, existing=snoozed,
        now=_at(12) + timedelta(days=31),
    )
    assert not during.alerts and after.alerts


def test_quiet_hours_defer_everything_but_the_critical(user):
    scenario = build("illiquid")
    analysis, recommendations = _run(scenario)
    run = filter_alerts(detect(analysis, recommendations), user=user, now=_at(23))
    assert all(a.severity is Priority.CRITICAL for a in run.alerts)
    assert run.deferred


def test_a_first_run_does_not_fire_ten_alerts_at_once(analysis, recommendations, user):
    """The moment a new user decides whether this is useful or is another thing
    that buzzes."""
    run = filter_alerts(detect(analysis, recommendations), user=user, now=_at(10))
    assert len(run.alerts) <= sum(PER_RUN_CAP.values())
    assert run.digest and run.digest_line


def test_feedback_reorders_but_never_silences(analysis, recommendations, user):
    feedback = [AlertFeedback("allocation_breach", useful=0, not_useful=9)]
    run = filter_alerts(detect(analysis, recommendations), user=user,
                        feedback=feedback, now=_at(10))
    delivered = [a.alert_type for a in run.alerts] + [a.alert_type for a in run.digest]
    assert "allocation_breach" in delivered


def test_feedback_needs_evidence_before_it_shifts_anything():
    assert AlertFeedback("x", useful=0, not_useful=1).shift() == 0
    assert AlertFeedback("x", useful=0, not_useful=5).shift() == 1


def test_feedback_is_summarised_from_stored_alerts():
    alerts = [
        Alert(id="a1", user_id="u", alert_type="t", severity=Priority.LOW, title="",
              body="", useful=True),
        Alert(id="a2", user_id="u", alert_type="t", severity=Priority.LOW, title="",
              body="", useful=False),
    ]
    summary = summarise_feedback(alerts)[0]
    assert summary.useful == 1 and summary.not_useful == 1
    assert summary.usefulness == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def test_the_daily_brief_says_nothing_when_nothing_is_wrong():
    analysis, recommendations = _run(build("balanced"))
    report = daily_brief(analysis, recommendations)
    assert report.nothing_to_do
    assert any("nothing" in section.title.lower() or "why" in section.title.lower()
               for section in report.sections)


def test_the_daily_brief_leads_with_what_needs_attention(analysis, recommendations):
    report = daily_brief(analysis, recommendations)
    assert not report.nothing_to_do
    assert "Where you stand" == report.sections[0].title


def test_the_brief_reports_change_against_a_previous_analysis(analysis, recommendations):
    report = daily_brief(analysis, recommendations, previous=analysis)
    assert any("Change since" in line for line in report.sections[0].lines)


def test_the_weekly_report_shows_every_band(analysis, recommendations):
    report = weekly_report(analysis, recommendations)
    allocation = next(s for s in report.sections if "Allocation" in s.title)
    assert len(allocation.lines) == len(analysis.drift.drifts)


def test_the_monthly_committee_leads_with_policy(analysis, recommendations):
    """A real investment committee paper puts performance last; it is the
    output of the process, not the agenda."""
    report = monthly_committee(analysis, recommendations)
    titles = [s.title for s in report.sections]
    assert titles[0].endswith("Policy")
    assert any("Adherence" in t for t in titles)
    assert any("Risk" in t for t in titles)
    assert any("Tax" in t for t in titles)


def test_the_monthly_committee_discloses_the_risk_gap(analysis, recommendations):
    report = monthly_committee(analysis, recommendations)
    policy = report.sections[0]
    assert any("capacity" in line for line in policy.lines)


def test_the_committee_notes_what_was_held_back(analysis, recommendations):
    report = monthly_committee(analysis, recommendations)
    decisions = next(s for s in report.sections if s.title.endswith("Decisions"))
    if recommendations.suppressed:
        assert any("held back" in line for line in decisions.lines)


def test_reports_render_to_text_and_json(analysis, recommendations):
    for report in (daily_brief(analysis, recommendations),
                   weekly_report(analysis, recommendations),
                   monthly_committee(analysis, recommendations)):
        assert report.render().strip()
        assert report.to_dict()["sections"]
