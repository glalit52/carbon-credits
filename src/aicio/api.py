"""HTTP API.

Standard library, for the same reason the rest of this package has no
dependencies: the same checkout runs on a laptop, in a container and on a
serverless function with nothing but Python. It is a real API -- routing,
typed handlers, JSON errors, bearer auth -- but it is a single-process server,
so put it behind a proper ASGI stack before it faces the internet.

Two boundaries are enforced here rather than assumed:

*   **Reads and writes are separated by authentication, and execution is
    separated from both.** There is no endpoint in this file that places a
    trade. Approving a recommendation records an approval; that is all.
*   **Nothing returns a number the engine did not produce.** Every analytical
    endpoint serialises a :class:`~aicio.analysis.PortfolioAnalysis` or a
    recommendation built from one.
"""

from __future__ import annotations

import json
import os
import re
import traceback
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from . import ENGINE_VERSION, __version__
from .ai import AIBanker, build_gateway
from .alerts import detect, filter_alerts, summarise_feedback
from .analysis import analyse
from .decisions import generate
from .domain import Conversation, DecisionOutcome, DecisionRecord, new_id
from .ingest import parse_statement
from .ingest.normalize import normalise
from .ips import generate_policy
from .market.connectors import ConsentError, default_registry
from .market.quotes import build_resolver
from .money import as_float
from .reports import daily_brief, monthly_committee, weekly_report
from .store import Store, StoreError

Handler = Callable[..., Any]
_ROUTES: list[tuple[str, re.Pattern, Handler]] = []


def route(method: str, pattern: str):
    """Register a handler. ``{name}`` in the pattern becomes a keyword argument."""
    regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$")

    def wrap(fn: Handler) -> Handler:
        _ROUTES.append((method, regex, fn))
        return fn
    return wrap


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra: Any):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra


# ---------------------------------------------------------------------------
# Analysis cache
# ---------------------------------------------------------------------------

#: Monte Carlo over three goals costs real CPU, and the dashboard, the action
#: centre and the chat all want the same analysis within seconds of each other.
#: Keyed on the portfolio fingerprint, so a changed portfolio always recomputes.
_ANALYSIS_CACHE: dict[str, Any] = {}

#: Simulation trials per goal. Tunable because the trade-off is deployment
#: specific: more trials tighten the tail estimates that matter for a goal
#: probability, and cost linear CPU on every cold analysis. The default is
#: enough that the reported percentiles are stable to about a tenth of a
#: percentage point.
MC_TRIALS = int(os.environ.get("AICIO_MC_TRIALS", "1500"))


def _context(store: Store, user_id: str, *, today: date | None = None):
    """Load, analyse and cache. The single entry point for every read."""
    portfolio = store.load_portfolio(user_id)
    if not portfolio.holdings:
        raise ApiError(404, f"no portfolio for {user_id!r}; import a statement first")
    profile = store.load_profile(user_id)
    goals = store.load_goals(user_id)
    policy_raw = store.load_policy(user_id)
    policy = generate_policy(profile, goals, today=today or portfolio.as_of)
    if policy_raw:
        policy = _policy_from(policy_raw, fallback=policy)

    fingerprint = portfolio.fingerprint()
    cached = _ANALYSIS_CACHE.get(user_id)
    if cached and cached["fingerprint"] == fingerprint and cached["policy"] == policy.id:
        return cached["analysis"], cached["recommendations"], portfolio, profile, policy

    analysis = analyse(portfolio, profile, policy, goals, today=today or portfolio.as_of,
                       monte_carlo_trials=MC_TRIALS)
    history = store.decision_history(user_id)
    recommendations = generate(analysis, today=analysis.as_of, history=history, limit=0)
    _ANALYSIS_CACHE[user_id] = {
        "fingerprint": fingerprint, "policy": policy.id,
        "analysis": analysis, "recommendations": recommendations,
    }
    return analysis, recommendations, portfolio, profile, policy


def _policy_from(raw: dict[str, Any], *, fallback):
    """Rehydrate a stored policy, keeping user edits over regenerated defaults."""
    from .ips import AllocationBand, Constraint, InvestmentPolicy
    from .domain import AssetClass
    return InvestmentPolicy(
        id=raw["id"], user_id=raw["user_id"],
        bands=[
            AllocationBand(AssetClass(b["asset_class"]), b["target"], b["lower"], b["upper"])
            for b in raw["bands"]
        ],
        constraints=[
            Constraint(c["id"], c["description"], c["kind"], c.get("limit"),
                       tuple(c.get("subjects", ())), c.get("hard", True))
            for c in raw["constraints"]
        ],
        objective=raw["objective"], horizon_years=raw["horizon_years"],
        review_frequency_months=raw.get("review_frequency_months", 6),
        rebalance_threshold=raw.get("rebalance_threshold", 0.05),
        min_emergency_months=raw.get("min_emergency_months", 6),
        version=raw.get("version", 1),
        edited_by_user=raw.get("edited_by_user", False),
        notes=list(raw.get("notes", [])),
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@route("GET", "/api/health")
def api_health(store: Store, **_) -> dict:
    gateway = build_gateway()
    return {
        "status": "ok",
        "version": __version__,
        "engine_version": ENGINE_VERSION,
        "store": store.health(),
        "ai": gateway.health(),
        "connectors": default_registry().available(),
    }


@route("GET", "/api/users/{user_id}/dashboard")
def api_dashboard(store: Store, user_id: str, **_) -> dict:
    """Everything the home screen needs, in one call.

    One request rather than six because the home screen's job is to answer
    "what needs attention now" in the time it takes to glance at it, and six
    round trips is how that becomes a loading spinner.
    """
    analysis, recommendations, portfolio, profile, policy = _context(store, user_id)
    alerts = filter_alerts(
        detect(analysis, recommendations),
        user=store.load_user(user_id),
        existing=store.load_alerts(user_id, include_closed=True),
        feedback=summarise_feedback(store.load_alerts(user_id, include_closed=True)),
    )
    return {
        "as_of": analysis.as_of.isoformat(),
        "net_worth": round(analysis.net_worth, 2),
        "market_value": round(as_float(portfolio.market_value), 2),
        "invested": round(as_float(portfolio.invested), 2),
        "cash": round(as_float(portfolio.cash), 2),
        "unrealised_gain": round(as_float(portfolio.unrealised_gain), 2),
        "xirr": analysis.portfolio_xirr,
        "health": analysis.health.to_dict(),
        "allocation": analysis.breakdown.to_dict(),
        "drift": analysis.drift.to_dict(),
        "goals": [p.to_dict() for p in analysis.projections],
        "actions": [r.to_dict() for r in recommendations.top],
        "do_nothing": recommendations.do_nothing,
        "alerts": [a.to_dict() for a in alerts.alerts],
        "alert_digest": alerts.digest_line,
        "engine_version": analysis.engine_version,
        "fingerprint": analysis.fingerprint,
    }


@route("GET", "/api/users/{user_id}/analysis")
def api_analysis(store: Store, user_id: str, **_) -> dict:
    analysis, _, _, _, _ = _context(store, user_id)
    return analysis.to_dict()


@route("GET", "/api/users/{user_id}/portfolio")
def api_portfolio(store: Store, user_id: str, **_) -> dict:
    analysis, _, portfolio, _, _ = _context(store, user_id)
    return {
        "as_of": portfolio.as_of.isoformat(),
        "accounts": [
            {"id": a.id, "institution": a.institution, "type": a.account_type.value,
             "masked": a.identifier_masked, "source": a.source.value}
            for a in portfolio.accounts
        ],
        "holdings": [h.to_dict() for h in analysis.holdings],
        "allocation": analysis.breakdown.to_dict(),
        "concentration": analysis.concentration.to_dict(),
    }


@route("GET", "/api/users/{user_id}/xray")
def api_xray(store: Store, user_id: str, **_) -> dict:
    analysis, _, _, _, _ = _context(store, user_id)
    return {
        **analysis.xray.to_dict(),
        "overlaps": [o.to_dict() for o in analysis.overlaps],
    }


@route("GET", "/api/users/{user_id}/actions")
def api_actions(store: Store, user_id: str, **_) -> dict:
    _, recommendations, _, _, _ = _context(store, user_id)
    return recommendations.to_dict()


@route("GET", "/api/users/{user_id}/goals")
def api_goals(store: Store, user_id: str, **_) -> dict:
    analysis, _, _, _, _ = _context(store, user_id)
    return {"goals": [p.to_dict() for p in analysis.projections]}


@route("GET", "/api/users/{user_id}/risk")
def api_risk(store: Store, user_id: str, **_) -> dict:
    analysis, _, _, _, _ = _context(store, user_id)
    return {
        "scenarios": [s.to_dict() for s in analysis.scenarios],
        "concentration": analysis.concentration.to_dict(),
        "liquid_months": analysis.liquid_months,
        "risk_capacity": analysis.profile.risk_capacity,
        "risk_tolerance": analysis.profile.risk_tolerance,
    }


@route("GET", "/api/users/{user_id}/tax")
def api_tax(store: Store, user_id: str, **_) -> dict:
    analysis, _, _, _, _ = _context(store, user_id)
    return analysis.tax.to_dict()


@route("GET", "/api/users/{user_id}/sips")
def api_sips(store: Store, user_id: str, **_) -> dict:
    analysis, _, _, _, _ = _context(store, user_id)
    return analysis.sip_plan.to_dict()


@route("GET", "/api/users/{user_id}/policy")
def api_policy(store: Store, user_id: str, **_) -> dict:
    _, _, _, _, policy = _context(store, user_id)
    return policy.to_dict()


@route("GET", "/api/users/{user_id}/reports/{kind}")
def api_report(store: Store, user_id: str, kind: str, **_) -> dict:
    analysis, recommendations, _, _, _ = _context(store, user_id)
    if kind == "daily":
        alerts = filter_alerts(detect(analysis, recommendations),
                               user=store.load_user(user_id)).alerts
        report = daily_brief(analysis, recommendations, alerts)
    elif kind == "weekly":
        report = weekly_report(analysis, recommendations)
    elif kind == "monthly":
        report = monthly_committee(
            analysis, recommendations, history=store.decision_history(user_id)
        )
    else:
        raise ApiError(404, f"unknown report {kind!r}; expected daily, weekly or monthly")
    return {**report.to_dict(), "text": report.render()}


@route("GET", "/api/users/{user_id}/alerts")
def api_alerts(store: Store, user_id: str, **_) -> dict:
    return {"alerts": [a.to_dict() for a in store.load_alerts(user_id)]}


@route("GET", "/api/users/{user_id}/audit")
def api_audit(store: Store, user_id: str, **_) -> dict:
    intact, bad = store.verify_chain()
    return {
        "chain_intact": intact, "first_bad_event": bad,
        "events": store.audit_trail(user_id, limit=100),
    }


@route("GET", "/api/connectors")
def api_connectors(store: Store, **_) -> dict:
    return {"connectors": default_registry().available()}


@route("GET", "/api/market/quote/{symbol}")
def api_quote(store: Store, symbol: str, **_) -> dict:
    resolver = build_resolver()
    quote = resolver.quote(symbol)
    if quote is None:
        raise ApiError(
            404, f"no quote available for {symbol!r}",
            providers=[p.name for p in resolver.providers], errors=resolver.errors[-3:],
        )
    return quote.to_dict()


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

@route("POST", "/api/users/{user_id}/import")
def api_import(store: Store, user_id: str, body: dict, **_) -> dict:
    """Import a statement. ``body`` carries a filename and base64 content."""
    import base64

    filename = body.get("filename")
    content = body.get("content_base64")
    if not filename or not content:
        raise ApiError(400, "filename and content_base64 are required")
    try:
        data = base64.b64decode(content)
    except Exception as exc:                          # noqa: BLE001
        raise ApiError(400, f"content_base64 is not valid base64: {exc}") from exc

    result = parse_statement(Path(filename), data=data, user_id=user_id)
    existing = store.load_portfolio(user_id)
    portfolio, report = normalise(
        [result], user_id=user_id, existing=existing if existing.holdings else None,
    )
    store.save_portfolio(portfolio)
    _ANALYSIS_CACHE.pop(user_id, None)
    store.record("statement.imported", user_id=user_id, subject=filename,
                 payload={"confidence": result.confidence,
                          "holdings": len(result.holdings),
                          "exceptions": len(result.exceptions)})
    return {
        "parse": result.to_dict(),
        "normalisation": report.to_dict(),
        "portfolio": {"holdings": len(portfolio.holdings),
                      "market_value": round(as_float(portfolio.market_value), 2)},
    }


@route("POST", "/api/users/{user_id}/connect/{connector}")
def api_connect(store: Store, user_id: str, connector: str, body: dict, **_) -> dict:
    """Complete a connector's authorisation and pull an initial sync."""
    from .store.repo import EncryptedTokenVault

    registry = default_registry(EncryptedTokenVault(store))
    client = registry.get(connector)
    consent = client.exchange(user_id, body or {})
    try:
        result = client.fetch_holdings(user_id, consent)
    except ConsentError as exc:
        raise ApiError(403, str(exc)) from exc
    existing = store.load_portfolio(user_id)
    portfolio, report = normalise(
        [result], user_id=user_id, existing=existing if existing.holdings else None,
    )
    store.save_portfolio(portfolio)
    _ANALYSIS_CACHE.pop(user_id, None)
    store.record("account.connected", user_id=user_id, subject=connector,
                 payload={"consent": consent.id, "scope": list(consent.scope)})
    return {
        "connector": connector,
        "consent": consent.to_dict(),
        "imported": {"holdings": len(result.holdings), "accounts": len(result.accounts)},
        "normalisation": report.to_dict(),
    }


@route("POST", "/api/users/{user_id}/ask")
def api_ask(store: Store, user_id: str, body: dict, **_) -> dict:
    question = (body or {}).get("question", "").strip()
    if not question:
        raise ApiError(400, "question is required")
    analysis, recommendations, _, _, _ = _context(store, user_id)
    conversation_id = body.get("conversation_id") or new_id("conv", user_id, analysis.fingerprint)
    conversation = store.load_conversation(conversation_id) or Conversation(
        id=conversation_id, user_id=user_id
    )
    banker = AIBanker(analysis, recommendations)
    reply = banker.ask(question, conversation=conversation, document=body.get("document"))
    store.save_message(conversation, "user", question)
    store.save_message(
        conversation, "assistant", reply.text, fact_ids=reply.fact_ids,
        prompt_id=reply.prompt_id, model=reply.model,
        grounded=None if reply.grounding is None else reply.grounding.grounded,
    )
    store.record("banker.answered", user_id=user_id, subject=conversation_id,
                 payload={"tools": reply.tools_used, "blocked": reply.blocked,
                          "prompt_id": reply.prompt_id})
    return {"conversation_id": conversation_id, **reply.to_dict()}


@route("POST", "/api/users/{user_id}/decisions")
def api_decision(store: Store, user_id: str, body: dict, **_) -> dict:
    """Record what the user decided about a recommendation.

    Note what this does not do: it does not execute anything. Recommending and
    executing are separate systems, and this endpoint lives entirely on the
    recommending side. An execution integration would sit behind its own
    service, its own permissions and its own compliance review.
    """
    recommendation_id = (body or {}).get("recommendation_id")
    outcome = (body or {}).get("outcome", "")
    if not recommendation_id or outcome not in {o.value for o in DecisionOutcome}:
        raise ApiError(
            400, "recommendation_id and a valid outcome are required",
            valid_outcomes=[o.value for o in DecisionOutcome],
        )
    record = DecisionRecord(
        id=new_id("dec", user_id, recommendation_id),
        user_id=user_id, recommendation_id=recommendation_id,
        outcome=DecisionOutcome(outcome), note=(body or {}).get("note", ""),
    )
    store.record_decision(record)
    _ANALYSIS_CACHE.pop(user_id, None)
    return {"recorded": True, "recommendation_id": recommendation_id, "outcome": outcome}


@route("POST", "/api/users/{user_id}/alerts/{alert_id}/feedback")
def api_alert_feedback(store: Store, user_id: str, alert_id: str, body: dict, **_) -> dict:
    from .alerts import mark, snooze

    alerts = {a.id: a for a in store.load_alerts(user_id, include_closed=True)}
    alert = alerts.get(alert_id)
    if alert is None:
        raise ApiError(404, f"no alert {alert_id!r}")
    action = (body or {}).get("action")
    if action == "snooze":
        snooze(alert, days=int((body or {}).get("days", 30)))
    elif action in {"useful", "not_useful"}:
        mark(alert, useful=action == "useful")
    else:
        raise ApiError(400, "action must be useful, not_useful or snooze")
    store.save_alerts([alert])
    store.record("alert.feedback", user_id=user_id, subject=alert_id, payload={"action": action})
    return {"alert": alert.to_dict()}


@route("DELETE", "/api/users/{user_id}")
def api_erase(store: Store, user_id: str, **_) -> dict:
    """Erasure. The audit log survives; it is what proves the erasure happened."""
    counts = store.delete_user_data(user_id)
    _ANALYSIS_CACHE.pop(user_id, None)
    return {"erased": True, "rows_deleted": counts}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(
    store: Store, method: str, path: str, query: dict, body: dict,
) -> tuple[int, dict]:
    for route_method, regex, handler in _ROUTES:
        if route_method != method:
            continue
        match = regex.match(path)
        if match is None:
            continue
        try:
            payload = handler(store=store, body=body, query=query, **match.groupdict())
            return 200, payload
        except ApiError as exc:
            return exc.status, {"error": exc.message, **exc.extra}
        except StoreError as exc:
            return 404, {"error": str(exc)}
        except ConsentError as exc:
            return 403, {"error": str(exc)}
        except Exception as exc:                       # noqa: BLE001
            return 500, {"error": f"{type(exc).__name__}: {exc}",
                         "trace": traceback.format_exc(limit=4).splitlines()[-4:]}
    return 404, {"error": f"no route for {method} {path}"}


def _authorised(headers: Any) -> bool:
    """Bearer token check. Open when no token is configured, which is the
    correct default for a local single-user run and an explicit, visible
    decision rather than a hidden one."""
    expected = os.environ.get("AICIO_API_TOKEN", "")
    if not expected:
        return True
    supplied = (headers.get("Authorization") or "").removeprefix("Bearer ").strip()
    return bool(supplied) and supplied == expected


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "aicio"
    store: Store

    def log_message(self, fmt: str, *args: Any) -> None:
        # Access logs belong in the process's structured log, not on stderr.
        pass

    def _send(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, indent=2, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _handle(self, method: str) -> None:
        if not _authorised(self.headers):
            self._send(401, {"error": "a bearer token is required"})
            return
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        body: dict = {}
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            try:
                body = json.loads(self.rfile.read(length).decode())
            except json.JSONDecodeError:
                self._send(400, {"error": "request body is not valid JSON"})
                return
        status, payload = dispatch(self.store, method, parsed.path, query, body)
        self._send(status, payload)

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_DELETE(self) -> None:
        self._handle("DELETE")


def serve(store: Store, *, host: str = "127.0.0.1", port: int = 8787) -> None:
    handler = type("BoundHandler", (ApiHandler,), {"store": store})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"aicio api on http://{host}:{port}  (engine {ENGINE_VERSION})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
