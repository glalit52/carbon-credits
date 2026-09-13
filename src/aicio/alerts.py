"""Proactive alerts, and the machinery that stops them becoming noise.

An alert system is judged entirely on its false positives. The tenth
unnecessary push is the one after which every subsequent alert -- including
the one that mattered -- is dismissed unread, so every control here exists to
make the system quieter rather than louder:

*   **Dedupe on state, not on notification.** The key is a hash of the
    condition, so the same breach re-detected tomorrow is the same alert, not
    a new one.
*   **Suppress until the state changes materially.** A 2% move inside an
    existing breach is not news.
*   **Respect quiet hours**, and hold anything short of critical until morning.
*   **Learn from feedback on ranking only.** A user who dismisses liquidity
    warnings sees them lower, never never. Feedback must not be able to switch
    off a financial control.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable, Sequence

from .analysis import PortfolioAnalysis
from .decisions.engine import RecommendationSet
from .domain import (
    Alert, AlertStatus, Priority, User, new_id,
)
from .money import format_money
from .provenance import utcnow

#: How much the underlying number must move before a suppressed alert is
#: allowed to fire again. Below this, the user already knows.
MATERIAL_CHANGE = 0.25

#: Feedback moves an alert type by at most this much, so a dismissal habit can
#: reorder the queue but never silence a control.
MAX_FEEDBACK_SHIFT = 1

#: How many alerts of each severity may be delivered in one run. Everything
#: above the cap is rolled into a digest line rather than sent.
#:
#: Without this, a first import fires ten alerts at once -- which is precisely
#: the moment a new user decides whether this product is useful or is another
#: thing that buzzes. Critical is capped at two because if there are genuinely
#: three critical problems, the third can wait ten minutes.
PER_RUN_CAP = {Priority.CRITICAL: 2, Priority.HIGH: 2, Priority.MEDIUM: 2, Priority.LOW: 1}


@dataclass
class AlertFeedback:
    """What the user has told us about a kind of alert."""

    alert_type: str
    useful: int = 0
    not_useful: int = 0
    snoozed: int = 0

    @property
    def usefulness(self) -> float:
        total = self.useful + self.not_useful
        return 0.5 if total == 0 else self.useful / total

    def shift(self) -> int:
        """Positions to move this alert type down the queue (never up past 0)."""
        if self.useful + self.not_useful < 3:
            return 0                       # not enough evidence to act on
        if self.usefulness < 0.34:
            return MAX_FEEDBACK_SHIFT
        return 0


def dedupe_key(alert_type: str, subject: str, bucket: Any) -> str:
    """Identity of the *state*.

    ``bucket`` is the condition quantised -- an allocation breach rounded to
    the nearest 2.5 points, say -- so ordinary drift inside a known breach
    keeps the same key and does not re-alert, while a real deterioration
    produces a new one.
    """
    payload = f"{alert_type}|{subject}|{bucket}"
    return "ak_" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def _bucket(value: float, step: float = 0.025) -> str:
    return f"{round(value / step) * step:.3f}"


@dataclass
class AlertRun:
    alerts: list[Alert]
    suppressed: list[tuple[Alert, str]] = field(default_factory=list)
    deferred: list[Alert] = field(default_factory=list)
    #: What was found but held back for volume. Shown in the app, not pushed.
    digest: list[Alert] = field(default_factory=list)

    @property
    def critical(self) -> list[Alert]:
        return [a for a in self.alerts if a.severity == Priority.CRITICAL]

    @property
    def digest_line(self) -> str:
        if not self.digest:
            return ""
        kinds = sorted({a.alert_type.replace("_", " ") for a in self.digest})
        return (
            f"{len(self.digest)} further item(s) are waiting in the app: "
            + ", ".join(kinds)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "alerts": [a.to_dict() for a in self.alerts],
            "suppressed": [{"id": a.id, "type": a.alert_type, "reason": reason}
                           for a, reason in self.suppressed],
            "deferred": [a.to_dict() for a in self.deferred],
            "digest": [a.to_dict() for a in self.digest],
            "digest_line": self.digest_line,
        }


def detect(
    analysis: PortfolioAnalysis,
    recommendations: RecommendationSet,
    *,
    now: datetime | None = None,
) -> list[Alert]:
    """Turn the analysis into candidate alerts.

    Alerts are not just recommendations with a bell on them. Some conditions
    deserve a notification without implying an action (a goal slipping), and
    some recommendations deserve no notification at all (a low-priority
    housekeeping item the user will see next time they open the app).
    """
    now = now or utcnow()
    user_id = analysis.user_id
    out: list[Alert] = []

    def add(alert_type: str, severity: Priority, title: str, body: str, key: str,
            recommendation_id: str = "", fact_names: Sequence[str] = ()) -> None:
        out.append(Alert(
            id=new_id("alert", user_id, key, now.date().isoformat()),
            user_id=user_id, alert_type=alert_type, severity=severity,
            title=title, body=body, dedupe_key=key, created_at=now, updated_at=now,
            recommendation_id=recommendation_id,
            fact_ids=tuple(f.id for f in analysis.facts.facts if f.name in set(fact_names)),
        ))

    # Liquidity first: it is the only condition that can force a bad sale.
    if analysis.liquid_months is not None:
        required = analysis.policy.min_emergency_months
        if analysis.liquid_months < required * 0.75:
            add("liquidity_breach", Priority.CRITICAL,
                "Emergency cover has fallen below the plan",
                f"Liquid assets cover {analysis.liquid_months:.1f} months of expenses "
                f"against a {required}-month minimum.",
                dedupe_key("liquidity_breach", "portfolio", _bucket(analysis.liquid_months, 0.5)),
                fact_names=("liquid_months",))

    for item in analysis.drift.breaches:
        add("allocation_breach",
            Priority.HIGH if abs(item.breach) > 0.08 else Priority.MEDIUM,
            f"{item.asset_class.value.title()} is outside its policy band",
            f"{item.asset_class.value.title()} is at {item.actual:.1%} against a band of "
            f"{item.lower:.0%}-{item.upper:.0%}.",
            dedupe_key("allocation_breach", item.asset_class.value, _bucket(item.breach)),
            fact_names=(f"drift.{item.asset_class.value}",))

    for name in analysis.single_names[:3]:
        add("concentration",
            Priority.HIGH if name.weight > analysis.policy.max_single_holding * 1.5
            else Priority.MEDIUM,
            f"{name.label} is {name.weight:.0%} of your portfolio",
            f"Policy allows {analysis.policy.max_single_holding:.0%} in any single company, "
            f"measured through your funds as well as your direct holdings.",
            dedupe_key("concentration", name.key, _bucket(name.weight)),
            fact_names=(f"single_name.{name.key}",))

    for projection in analysis.projections:
        if projection.status in {"off_track", "at_risk"}:
            add("goal_deterioration",
                Priority.HIGH if projection.status == "off_track" else Priority.MEDIUM,
                f"'{projection.goal_name}' is {projection.status.replace('_', ' ')}",
                f"Probability of reaching the target is {projection.probability:.0%}. "
                f"About {format_money(projection.required_monthly)} a month would be needed "
                "on current assumptions.",
                dedupe_key("goal_deterioration", projection.goal_id,
                           _bucket(projection.probability, 0.1)),
                fact_names=(f"goal.{projection.goal_id}.probability",))

    if analysis.liquid_months is not None:
        excess = analysis.liquid_months - (analysis.policy.min_emergency_months + 3)
        if excess > 1:
            add("cash_buildup", Priority.LOW, "Cash is building up",
                f"Liquid assets cover {analysis.liquid_months:.0f} months of expenses, "
                f"{excess:.0f} more than the plan needs.",
                dedupe_key("cash_buildup", "portfolio", _bucket(analysis.liquid_months, 1.0)),
                fact_names=("liquid_months", "cash"))

    from .money import as_float
    if as_float(analysis.tax.ltcg_exemption_left) > 50000 and analysis.as_of.month >= 11:
        add("tax_opportunity", Priority.MEDIUM,
            "Unused capital-gains exemption this financial year",
            f"{format_money(analysis.tax.ltcg_exemption_left)} of the annual exemption "
            "has not been used. It does not carry forward.",
            dedupe_key("tax_opportunity", "ltcg",
                       f"{analysis.as_of.year}-{as_float(analysis.tax.ltcg_exemption_left) // 25000}"),
            fact_names=("tax.ltcg_exemption_left",))

    if analysis.portfolio.stale_holdings():
        stale = len(analysis.portfolio.stale_holdings())
        add("data_freshness", Priority.LOW,
            f"{stale} holdings need refreshing",
            "Prices for some positions are outside their freshness window, so the "
            "figures shown are approximate.",
            dedupe_key("data_freshness", "portfolio", str(stale)))

    # Attach the recommendation that answers each alert, where one exists.
    by_subject = {r.subject_id: r for r in recommendations.recommendations}
    for alert in out:
        if alert.recommendation_id:
            continue
        for subject, recommendation in by_subject.items():
            if subject in alert.dedupe_key or subject in alert.title:
                alert.recommendation_id = recommendation.id
                break
    return out


def filter_alerts(
    candidates: Sequence[Alert],
    *,
    user: User,
    existing: Sequence[Alert] = (),
    feedback: Sequence[AlertFeedback] = (),
    now: datetime | None = None,
) -> AlertRun:
    """Apply de-duplication, snoozes, quiet hours and feedback ordering."""
    now = now or utcnow()
    known = {alert.dedupe_key: alert for alert in existing}
    shifts = {item.alert_type: item.shift() for item in feedback}

    kept: list[Alert] = []
    suppressed: list[tuple[Alert, str]] = []
    deferred: list[Alert] = []

    for alert in candidates:
        previous = known.get(alert.dedupe_key)
        if previous is not None:
            if previous.status == AlertStatus.DISMISSED:
                suppressed.append((alert, "already dismissed; state has not changed materially"))
                continue
            if previous.status == AlertStatus.SNOOZED and previous.snooze_until and \
                    previous.snooze_until > now:
                suppressed.append((alert, f"snoozed until {previous.snooze_until.isoformat()}"))
                continue
            if previous.status == AlertStatus.OPEN:
                suppressed.append((alert, "already open and unchanged"))
                continue
        kept.append(alert)

    # Quiet hours defer everything except the critical.
    ready: list[Alert] = []
    for alert in kept:
        if alert.severity != Priority.CRITICAL and user.in_quiet_hours(now):
            deferred.append(alert)
            continue
        ready.append(alert)

    from .domain import PRIORITY_RANK
    ready.sort(key=lambda a: (
        PRIORITY_RANK[a.severity] + (shifts.get(a.alert_type, 0)
                                     if a.severity != Priority.CRITICAL else 0),
        a.alert_type,
    ))

    delivered: list[Alert] = []
    digest: list[Alert] = []
    counts: dict[Priority, int] = {}
    for alert in ready:
        used = counts.get(alert.severity, 0)
        if used >= PER_RUN_CAP.get(alert.severity, 2):
            digest.append(alert)
            continue
        counts[alert.severity] = used + 1
        delivered.append(alert)

    return AlertRun(
        alerts=delivered, suppressed=suppressed, deferred=deferred, digest=digest,
    )


def snooze(alert: Alert, *, days: int = 30, now: datetime | None = None) -> Alert:
    now = now or utcnow()
    alert.status = AlertStatus.SNOOZED
    alert.snooze_until = now + timedelta(days=days)
    alert.updated_at = now
    return alert


def mark(alert: Alert, *, useful: bool, now: datetime | None = None) -> Alert:
    alert.useful = useful
    alert.updated_at = now or utcnow()
    if not useful:
        alert.status = AlertStatus.DISMISSED
    return alert


def summarise_feedback(alerts: Iterable[Alert]) -> list[AlertFeedback]:
    tally: dict[str, AlertFeedback] = {}
    for alert in alerts:
        item = tally.setdefault(alert.alert_type, AlertFeedback(alert.alert_type))
        if alert.useful is True:
            item.useful += 1
        elif alert.useful is False:
            item.not_useful += 1
        if alert.status == AlertStatus.SNOOZED:
            item.snoozed += 1
    return list(tally.values())
