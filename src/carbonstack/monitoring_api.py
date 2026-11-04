"""Field loggers, the scene catalogue and registry exports, for the web app.

Three checks a project runs against the world outside its own ledger, each a
request/response so the read-only deployment can serve them:

* `sensors_request`: a water-level logger file is cleaned (gaps, flatlines,
  spikes) and reduced to one water state per day. If the farm's radar calls
  are supplied too, the detector is scored against what the logger measured.
* `scenes_request`: which Sentinel-1/2 scenes actually exist over a farm in a
  window, and the longest gap between usable ones -- the number a monitoring
  plan is judged on.
* `reconcile_request`: our issued vintages against a registry's CSV export,
  matched by serial block, then reference, then vintage and quantity.

Nothing is stored. The web app keeps what comes back.
"""

from __future__ import annotations

from datetime import date, timedelta

from .connectors import ConnectorUnavailable, default_transport
from .connectors import registry as registry_mod
from .connectors import sensors, stac
from .ledger import Issuance
from .sar import Classification, WaterState

MAX_SCENE_DAYS = 400


class MonitoringError(ValueError):
    """The request cannot be served; the message says what to fix."""


def _date(value, name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise MonitoringError(f"{name} must be a date (YYYY-MM-DD)") from exc


def _calls(raw: list[dict]) -> list[Classification]:
    out = []
    for i, c in enumerate(raw):
        try:
            out.append(Classification(
                day=date.fromisoformat(c["day"]), state=WaterState(c["state"]),
                p_flooded=float(c["p_flooded"]),
                stage_estimate=float(c.get("stage_estimate", 0.0)),
                separation_db=float(c.get("separation_db", 0.0)),
                vv_normalised_db=float(c.get("vv_db", 0.0)),
                inferred=bool(c.get("inferred", False))))
        except (KeyError, TypeError, ValueError) as exc:
            raise MonitoringError(f"radar call {i + 1} is malformed ({exc})") from exc
    return out


def sensors_request(body: dict) -> dict:
    """Clean a logger file and, given radar calls, score the detector on it."""
    text = body.get("csv")
    fmt = "csv"
    if not text and body.get("json"):
        text, fmt = body["json"], "json"
    if not text or not str(text).strip():
        raise MonitoringError("send the logger file as csv (or json)")
    try:
        readings = (sensors.parse_csv if fmt == "csv" else sensors.parse_json)(str(text))
    except (ValueError, KeyError) as exc:
        raise MonitoringError(str(exc)) from exc
    if not readings:
        raise MonitoringError("the file has no readings")

    plot = body.get("plot_id")
    if plot:
        # A logger file from a gateway carries every plot it serves; the farm
        # page asks about one. Readings for other plots are left out, and said so.
        others = {r.plot_id for r in readings if r.plot_id != plot}
        mine = [r for r in readings if r.plot_id == plot]
        if not mine and len({r.plot_id for r in readings}) == 1:
            mine, others = readings, set()      # one plot, under the logger's own id
        readings = mine
        if not readings:
            raise MonitoringError(f"no readings for plot {plot!r} in this file")
    else:
        others = set()

    records = sensors.clean(readings)
    out = {
        "readings": len(readings),
        "other_plots": sorted(others),
        "records": [r.to_dict() for r in records],
        "days": [
            {"device_id": r.device_id, "day": d.day.isoformat(), "mean_cm": round(d.mean_cm, 1),
             "min_cm": round(d.min_cm, 1), "state": d.state.value}
            for r in records for d in r.days
        ],
        "thresholds": {
            "flooded_above_cm": sensors.FLOODED_ABOVE_CM,
            "drained_below_cm": sensors.DRAINED_BELOW_CM,
            "safe_awd_cm": sensors.SAFE_AWD_THRESHOLD_CM,
        },
        "validation": None,
    }
    radar = body.get("radar") or []
    usable = [r for r in records if r.days]
    if radar and usable:
        out["validation"] = sensors.validate_detector(_calls(radar), usable).to_dict()
    return out


def scenes_request(body: dict, *, transport=None) -> dict:
    """Catalogue coverage over a farm's bounding box."""
    try:
        ring = body["boundary"]["coordinates"][0]
        bbox = stac.bbox_of([(float(x), float(y)) for x, y in ring])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise MonitoringError("boundary must be a GeoJSON Polygon") from exc
    end = _date(body.get("end") or date.today().isoformat(), "end")
    start = _date(body.get("start") or (end - timedelta(days=180)).isoformat(), "start")
    if not timedelta(0) < end - start <= timedelta(days=MAX_SCENE_DAYS):
        raise MonitoringError(f"the window must be 1 to {MAX_SCENE_DAYS} days")
    sensor = body.get("sensor", "s1")
    if sensor not in stac.COLLECTIONS:
        raise MonitoringError(f"sensor must be one of {sorted(stac.COLLECTIONS)}")
    try:
        cov = stac.search(transport or default_transport(), bbox=bbox, start=start,
                          end=end, sensor=sensor)
    except ConnectorUnavailable as exc:
        raise MonitoringError(f"scene catalogue unavailable: {exc}") from exc
    usable = set(cov.usable_days)
    return {
        **cov.to_dict(),
        "provenance": [{k: v for k, v in p.items() if k != "body"} for p in cov.provenance],
        "scene_list": [
            {"id": s.id, "day": s.day.isoformat(), "platform": s.platform,
             "cloud_cover": s.cloud_cover, "relative_orbit": s.relative_orbit,
             "orbit_state": s.orbit_state, "usable": s.day in usable}
            for s in sorted(cov.scenes, key=lambda s: s.acquired)
        ],
    }


def reconcile_request(body: dict) -> dict:
    """Our issued vintages against a registry export."""
    registry = str(body.get("registry") or "registry")
    text = body.get("csv")
    if not text or not str(text).strip():
        raise MonitoringError("send the registry export as csv")
    try:
        export = registry_mod.parse_export(str(text), registry=registry,
                                           overrides=body.get("columns") or None)
    except ValueError as exc:
        raise MonitoringError(str(exc)) from exc

    ours = []
    for i, v in enumerate(body.get("issuances") or []):
        try:
            year = int(v["year"])
            ours.append(Issuance(
                id=str(v["id"]), vintage_id=f"{v.get('project', 'project')}:{year}",
                quantity=int(v["quantity"]), serial_start=str(v.get("serial_start", "")),
                serial_end=str(v.get("serial_end", "")),
                issued_on=date.fromisoformat(v.get("issued_on") or f"{year}-12-31"),
                registry=registry, registry_ref=str(v.get("registry_ref") or "")))
        except (KeyError, TypeError, ValueError) as exc:
            raise MonitoringError(f"issuance {i + 1} is malformed ({exc})") from exc

    rec = registry_mod.reconcile(ours, export)
    return {
        **rec.to_dict(),
        "columns": export.columns,
        "ignored_columns": export.ignored_columns,
        "rows": len(export.rows),
        "matches": [
            {"issuance_id": m.issuance_id, "registry_line": m.registry_line,
             "basis": m.basis, "ours": m.ours, "theirs": m.theirs, "agrees": m.agrees}
            for m in rec.matches
        ],
        "unknown_rows": [
            {"line": r.line, "vintage": r.vintage, "quantity": r.quantity,
             "serial": r.serial, "status": r.status}
            for r in rec.unknown_to_us
        ],
    }
