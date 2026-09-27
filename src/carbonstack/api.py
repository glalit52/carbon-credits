"""HTTP API.

Built on the standard library on purpose. The core has no dependencies and
this keeps that true: the same checkout runs on a laptop, in a container and
on a field server with nothing but Python. It is a real API -- routing, typed
handlers, JSON errors, a bearer token -- but it is a single-process server, so
put it behind a proper ASGI stack before it faces the internet.

Reads are open to any authenticated caller. Writes are the acts that change a
commercial record -- approving a vintage, issuing credits, marking a payment
paid -- so each one takes an actor, and each one lands in the event chain
under that actor's name.
"""

from __future__ import annotations

import json
import os
import re
import traceback
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from . import agroforestry, article6, ledger, payments, stacking
from .pipeline import health
from .store.repo import Store, StoreError

Handler = Callable[..., Any]
_ROUTES: list[tuple[str, re.Pattern, Handler]] = []


def route(method: str, pattern: str):
    """Register a handler. `{name}` in the pattern becomes a keyword argument."""
    regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$")

    def wrap(fn: Handler) -> Handler:
        _ROUTES.append((method, regex, fn))
        return fn
    return wrap


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@route("GET", "/api/health")
def api_health(store: Store, **_) -> dict:
    intact, bad = store.verify_chain()
    return {
        "status": "ok",
        "database": store.path,
        "projects": len(store.list_projects()),
        "chain_intact": intact,
        "first_bad_event": bad,
    }


@route("GET", "/api/projects")
def api_projects(store: Store, **_) -> dict:
    return {"projects": store.list_projects()}


@route("GET", "/api/projects/{project_id}")
def api_project(store: Store, project_id: str, **_) -> dict:
    project = store.load_project(project_id)
    meta = store.project_meta(project_id)
    return {
        "id": project.id, "name": project.name, "track": project.track.value,
        "country": project.country,
        "start_date": project.start_date.isoformat(),
        "methodology": meta["methodology_id"],
        "registry": meta["registry"],
        "farmers": len(project.farmers),
        "plots": len(project.plots),
        "area_ha": round(project.area_ha, 4),
        "creditable_ha": round(project.creditable_area_ha(), 4),
    }


@route("GET", "/api/projects/{project_id}/health")
def api_project_health(store: Store, project_id: str, **_) -> dict:
    return health(store, project_id)


@route("GET", "/api/projects/{project_id}/plots")
def api_plots(store: Store, project_id: str, **_) -> dict:
    project = store.load_project(project_id)
    issues = project.eligibility_issues()
    return {"plots": [{
        "id": p.id, "farmer_id": p.farmer_id,
        "area_ha": round(p.area_ha, 4),
        "centroid": [round(v, 6) for v in p.centroid],
        "tenure": p.tenure.value,
        "tenure_reference": p.tenure_reference,
        "fingerprint": p.fingerprint,
        "creditable": p.id not in issues,
        "issues": issues.get(p.id, []),
    } for p in project.plots.values()]}


@route("GET", "/api/projects/{project_id}/eligibility")
def api_eligibility(store: Store, project_id: str, **_) -> dict:
    project = store.load_project(project_id)
    issues = project.eligibility_issues()
    reasons: dict[str, int] = {}
    for problems in issues.values():
        for p in problems:
            reasons[p] = reasons.get(p, 0) + 1
    return {
        "enrolled_ha": round(project.area_ha, 4),
        "creditable_ha": round(project.creditable_area_ha(), 4),
        "blocked_plots": len(issues),
        "reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        # Reported apart from the per-plot findings because these block every
        # hectare at once, and repeating them per plot would bury the rest.
        "programme_issues": project.programme_issues(),
        "methodology_version": store.project_meta(project_id)["methodology_version"],
        "detail": issues,
    }


@route("GET", "/api/projects/{project_id}/stacking")
def api_stacking(store: Store, project_id: str, **_) -> dict:
    """Is any hectare claimed twice. Read this before issuing on a stacked plot."""
    return stacking.audit(store, project_id)


@route("POST", "/api/projects/{project_id}/stacking")
def api_register_claim(store: Store, project_id: str, body: dict, **_) -> dict:
    try:
        pillar = stacking.Pillar(body["pillar"])
        methodology_id = body["methodology_id"]
        area_ha = float(body["area_ha"])
    except KeyError as exc:
        raise ApiError(400, f"missing field: {exc.args[0]}") from None
    except ValueError as exc:
        raise ApiError(400, str(exc)) from None

    plot_id = body.get("plot_id")
    if not plot_id:
        raise ApiError(400, "missing field: plot_id")

    geometry = body.get("geometry")
    if geometry is not None:
        geometry = [tuple(v) for v in geometry]

    return stacking.register_claim(
        store, project_id, plot_id, pillar=pillar,
        methodology_id=methodology_id, area_ha=area_ha, geometry=geometry,
        actor=_actor(body)).to_dict()


@route("GET", "/api/allometry")
def api_allometry(store: Store, **_) -> dict:
    """The equation catalogue, and which entries are still placeholders.

    Exposed because the gap between a generic equation and a local fit is
    roughly a quarter of a tree project's credits, and a buyer doing
    diligence should be able to read which one priced the tonnes they are
    being sold.
    """
    return {"species": [{
        "key": key,
        "name": sp.name,
        "equation": sp.equation,
        "wood_density_g_cm3": sp.wood_density_g_cm3,
        "root_shoot": sp.root_shoot,
        "relative_error": sp.relative_error,
        "locally_calibrated": sp.is_locally_calibrated,
        "region": sp.region,
        "source": sp.source,
    } for key, sp in sorted(agroforestry.SPECIES.items())]}


@route("GET", "/api/projects/{project_id}/trees")
def api_trees(store: Store, project_id: str, query: dict, **_) -> dict:
    """The census: what was counted, by whom, and what it is worth.

    `?year=` reads the inventory as it stood at the end of that year, which
    is the view a verifier checking a past vintage needs.
    """
    year = query.get("year")
    inventories = store.tree_inventories(
        project_id, year=int(year[0]) if year else None)

    plots = []
    for plot_id, inv in sorted(inventories.items()):
        survey = inv.survival
        stock, relative = inv.stock()
        plots.append({
            "plot_id": plot_id,
            "measured_on": inv.measured_on.isoformat(),
            "surveyed_on": survey.surveyed_on.isoformat(),
            "surveyor": survey.surveyor,
            "stems_planted": survey.stems_planted,
            "stems_sampled": survey.stems_sampled,
            "stems_alive": survey.stems_alive,
            "survival_rate": round(survey.survival_rate, 4),
            "survival_lower_bound": round(survey.survival_lower_bound(), 4),
            "stems_credited": survey.surviving_stems,
            "stems_measured": len(inv.sample),
            "mean_kgco2e_per_stem": round(inv.mean_co2e_per_stem_kg, 3),
            "stock_tco2e": round(stock, 4),
            "relative_uncertainty": round(relative, 4),
            "locally_calibrated": inv.uses_local_allometry,
            "needs_replanting": survey.needs_replanting,
            "issues": survey.issues(),
        })

    benchmark = agroforestry.BenchmarkProvider()
    return {
        "approach": "VM0047 v1.1 census-based",
        "plots": plots,
        "stems_planted": sum(p["stems_planted"] for p in plots),
        "stems_credited": sum(p["stems_credited"] for p in plots),
        "standing_stock_tco2e": round(sum(p["stock_tco2e"] for p in plots), 4),
        "plots_below_survival_floor": sum(
            1 for p in plots if p["needs_replanting"]),
        "benchmark_vetted": benchmark.is_vetted,
        "benchmark_note": (
            "performance benchmark is a placeholder; no issuance may rest on "
            "it until a Verra-vetted data service provider supplies one"
            if not benchmark.is_vetted else ""),
    }


@route("GET", "/api/projects/{project_id}/vintages")
def api_vintages(store: Store, project_id: str, **_) -> dict:
    return {"vintages": [v.to_dict()
                         for v in ledger.list_vintages(store, project_id)]}


@route("GET", "/api/vintages/{vintage_id}")
def api_vintage(store: Store, vintage_id: str, **_) -> dict:
    return ledger.get_vintage(store, vintage_id).to_dict()


@route("GET", "/api/vintages/{vintage_id}/derivation")
def api_derivation(store: Store, vintage_id: str, **_) -> dict:
    return {"vintage_id": vintage_id,
            "calculations": ledger.calculations(store, vintage_id)}


@route("GET", "/api/queue")
def api_queue(store: Store, **_) -> dict:
    """Everything waiting on a human, across every project."""
    waiting = [v for v in ledger.list_vintages(store)
               if v.status in (ledger.VintageStatus.DRAFT,
                               ledger.VintageStatus.UNDER_REVIEW,
                               ledger.VintageStatus.HELD)]
    return {"queue": [{**v.to_dict(), "needs_review": v.needs_review}
                      for v in waiting]}


@route("GET", "/api/projects/{project_id}/issuances")
def api_issuances(store: Store, project_id: str, **_) -> dict:
    return {
        "issuances": [i.to_dict() for i in ledger.issuances(store, project_id)],
        "buffer": ledger.buffer_balance(store, project_id),
    }


@route("GET", "/api/projects/{project_id}/payments")
def api_payments(store: Store, project_id: str, query: dict, **_) -> dict:
    status = query.get("status", [None])[0]
    rows = payments.register(
        store, project_id=project_id,
        status=payments.PaymentStatus(status) if status else None)
    return {"payments": [p.to_dict() for p in rows],
            "summary": payments.summary(store, project_id)}


@route("GET", "/api/projects/{project_id}/claims")
def api_claims(store: Store, project_id: str, query: dict, **_) -> dict:
    """What a buyer of each vintage may truthfully say.

    The page a buyer's counsel reads before signing, and the one a CORSIA
    auditor asks for.
    """
    ccts = query.get("ccts", ["false"])[0].lower() in ("1", "true", "yes")
    return article6.claim_register(store, project_id, ccts_registered=ccts)


@route("POST", "/api/projects/{project_id}/authorisations")
def api_authorise(store: Store, project_id: str, body: dict, **_) -> dict:
    from datetime import date as _date
    try:
        a = article6.record_authorisation(
            store, project_id,
            authority=body["authority"], reference=body["reference"],
            issued_on=_date.fromisoformat(body["issued_on"]),
            authorised_use=article6.AuthorisedUse(body["authorised_use"]),
            authorised_volume_t=float(body["authorised_volume_t"]),
            corresponding_adjustment_committed=bool(
                body.get("corresponding_adjustment_committed", False)),
            first_vintage=int(body["first_vintage"]),
            last_vintage=int(body["last_vintage"]),
            valid_until=(_date.fromisoformat(body["valid_until"])
                         if body.get("valid_until") else None),
            actor=_actor(body))
    except KeyError as exc:
        raise ApiError(400, f"missing field: {exc.args[0]}") from None
    return a.to_dict()


@route("POST", "/api/authorisations/{authorisation_id}/adjustments")
def api_adjust(store: Store, authorisation_id: str, body: dict, **_) -> dict:
    from datetime import date as _date
    try:
        adj = article6.record_adjustment(
            store, authorisation_id, vintage_year=int(body["vintage_year"]),
            volume_t=float(body["volume_t"]),
            applied_on=_date.fromisoformat(body["applied_on"]),
            reported_in=body["reported_in"], actor=_actor(body))
    except KeyError as exc:
        raise ApiError(400, f"missing field: {exc.args[0]}") from None
    return adj.to_dict()


@route("GET", "/api/events")
def api_events(store: Store, query: dict, **_) -> dict:
    events = store.events(query.get("subject_type", [None])[0],
                          query.get("subject_id", [None])[0])
    limit = int(query.get("limit", ["200"])[0])
    return {"events": [{k: v for k, v in e.items() if k != "payload_json"}
                       for e in events[-limit:]],
            "total": len(events)}


@route("GET", "/api/integrity")
def api_integrity(store: Store, **_) -> dict:
    intact, bad = store.verify_chain()
    events = store.events()
    return {"chain_intact": intact, "first_bad_event": bad,
            "event_count": len(events),
            "head_hash": events[-1]["hash"] if events else None}


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def _actor(body: dict) -> str:
    actor = (body.get("actor") or "").strip()
    if not actor:
        raise ApiError(400, "an 'actor' is required: every write is attributed")
    return actor


@route("POST", "/api/vintages/{vintage_id}/submit")
def api_submit(store: Store, vintage_id: str, body: dict, **_) -> dict:
    return ledger.submit_for_review(
        store, vintage_id, actor=_actor(body),
        note=body.get("note", "")).to_dict()


@route("POST", "/api/vintages/{vintage_id}/approve")
def api_approve(store: Store, vintage_id: str, body: dict, **_) -> dict:
    return ledger.approve(store, vintage_id, actor=_actor(body),
                          note=body.get("note", "")).to_dict()


@route("POST", "/api/vintages/{vintage_id}/hold")
def api_hold(store: Store, vintage_id: str, body: dict, **_) -> dict:
    return ledger.hold(store, vintage_id, actor=_actor(body),
                       note=body.get("note", "")).to_dict()


@route("POST", "/api/vintages/{vintage_id}/issue")
def api_issue(store: Store, vintage_id: str, body: dict, **_) -> dict:
    registry = (body.get("registry") or "").strip()
    if not registry:
        raise ApiError(400, "a 'registry' is required to issue")
    return ledger.issue(store, vintage_id, registry=registry,
                        registry_ref=body.get("registry_ref", ""),
                        actor=_actor(body)).to_dict()


@route("POST", "/api/vintages/{vintage_id}/payments")
def api_raise_payments(store: Store, vintage_id: str, body: dict, **_) -> dict:
    try:
        terms = payments.PaymentTerms(
            price_per_credit=float(body["price_per_credit"]),
            farmer_share=float(body["farmer_share"]),
            currency=body.get("currency", "USD"))
    except KeyError as exc:
        raise ApiError(400, f"missing field: {exc.args[0]}") from None
    except ValueError as exc:
        raise ApiError(400, str(exc)) from None
    made = payments.raise_payments(store, vintage_id, terms, actor=_actor(body))
    return {"raised": len(made), "payments": [p.to_dict() for p in made]}


@route("POST", "/api/payments/{payment_id}/approve")
def api_approve_payment(store: Store, payment_id: str, body: dict, **_) -> dict:
    return payments.approve_payment(store, payment_id,
                                    actor=_actor(body)).to_dict()


@route("POST", "/api/payments/{payment_id}/paid")
def api_mark_paid(store: Store, payment_id: str, body: dict, **_) -> dict:
    reference = (body.get("reference") or "").strip()
    if not reference:
        raise ApiError(400, "a payment 'reference' is required to mark it paid")
    return payments.mark_paid(store, payment_id, reference=reference,
                              paid_on=date.fromisoformat(body["paid_on"])
                              if body.get("paid_on") else None,
                              actor=_actor(body)).to_dict()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(store: Store, method: str, path: str, query: dict,
             body: dict) -> tuple[int, dict]:
    """Route one request. Separated from the HTTP layer so tests can call it."""
    for m, regex, fn in _ROUTES:
        if m != method:
            continue
        hit = regex.match(path)
        if not hit:
            continue
        try:
            return 200, fn(store=store, query=query, body=body, **hit.groupdict())
        except ApiError as exc:
            return exc.status, {"error": exc.message}
        except StoreError as exc:
            # A refused operation is the caller asking for something the rules
            # forbid, not a server fault. 409 says "your state assumption is
            # wrong", which is the useful thing for a client to know.
            return 409, {"error": str(exc)}
        except (KeyError, ValueError) as exc:
            return 400, {"error": str(exc)}
    return 404, {"error": f"no route for {method} {path}"}


def make_handler(store: Store, token: str | None):
    class ApiHandler(BaseHTTPRequestHandler):
        server_version = "carbonstack"

        def log_message(self, fmt: str, *args) -> None:
            print(f"  {self.command} {self.path} → {args[1] if len(args) > 1 else ''}")

        def _authorised(self) -> bool:
            if not token:
                return True
            header = self.headers.get("Authorization", "")
            return header == f"Bearer {token}"

        def _respond(self, status: int, payload: dict) -> None:
            raw = json.dumps(payload, indent=2, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _handle(self, method: str) -> None:
            if not self._authorised():
                self._respond(401, {"error": "bearer token required"})
                return
            parsed = urlparse(self.path)
            body: dict = {}
            if method == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    try:
                        body = json.loads(self.rfile.read(length) or b"{}")
                    except json.JSONDecodeError:
                        self._respond(400, {"error": "body is not valid JSON"})
                        return
                    if not isinstance(body, dict):
                        self._respond(400, {"error": "body must be a JSON object"})
                        return
            try:
                status, payload = dispatch(store, method, parsed.path,
                                           parse_qs(parsed.query), body)
            except Exception:
                traceback.print_exc()
                self._respond(500, {"error": "internal error"})
                return
            self._respond(status, payload)

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

    return ApiHandler


def serve(store: Store, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the API. Token comes from CARBONSTACK_TOKEN if set."""
    token = os.environ.get("CARBONSTACK_TOKEN")
    httpd = ThreadingHTTPServer((host, port), make_handler(store, token))
    print(f"carbonstack api on http://{host}:{port}  db={store.path}")
    print("  auth: " + ("bearer token required" if token
                        else "OPEN — set CARBONSTACK_TOKEN to require one"))
    print("  routes:")
    for m, regex, fn in sorted(_ROUTES, key=lambda r: (r[2].__name__)):
        print(f"    {m:<5} {regex.pattern[1:-1].replace('(?P<', '{').replace('>[^/]+)', '}')}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
