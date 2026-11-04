"""Loggers, the scene catalogue and registry exports, as the web app calls
them -- and the monitoring series every estimate now carries."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from carbonstack.api import dispatch
from carbonstack.connectors.base import ConnectorUnavailable, Snapshot
from carbonstack.estimate import estimate
from carbonstack.monitoring_api import (
    MonitoringError, reconcile_request, scenes_request, sensors_request,
)
from test_estimate import TODAY, rice_request, tree_request


def logger_csv(levels, *, device="WL-1", plot="farm-1"):
    lines = ["device_id,plot_id,timestamp,water_level_cm"]
    for day, level in levels:
        for h in range(0, 24, 3):
            at = datetime(day.year, day.month, day.day, h, tzinfo=timezone.utc)
            lines.append(f"{device},{plot},{at.isoformat()},{level + 0.1 * (h % 2):.2f}")
    return "\n".join(lines)


START = date(2025, 7, 1)
LEVELS = [(START + timedelta(days=i), 5 if i % 12 < 6 else -18) for i in range(36)]


# --- estimate monitoring -------------------------------------------------------

def test_a_rice_estimate_carries_the_radar_calls_it_was_built_from():
    out = estimate(rice_request(enrolled_on="2023-06-01"), today=TODAY)
    m = out["monitoring"]
    assert m["simulated"] is True
    assert m["years"] == [2024, 2025, 2026], "the last three years, not all of them"
    assert m["radar"] and {c["state"] for c in m["radar"]} <= {"flooded", "drained", "ambiguous"}
    assert all(c["day"][:4] in {"2024", "2025", "2026", "2027"} for c in m["radar"])
    seasons = {(r["year"], r["season"]) for r in m["regimes"]}
    assert (2025, "Kuruvai") in seasons
    # What the farm page plots is what quantification used: the season's
    # adoption confidence matches the regime the methodology read.
    v2025 = next(v for v in out["vintages"] if v["year"] == 2025)
    assert v2025["net_t"] >= 0
    assert all(0 <= r["adoption_confidence"] <= 1 for r in m["regimes"])


def test_a_tree_estimate_carries_canopy_not_radar():
    m = estimate(tree_request(), today=TODAY)["monitoring"]
    assert m["radar"] == [] and m["regimes"] == []
    assert any("canopy_m" in o for o in m["optical"])


# --- sensors ------------------------------------------------------------------

def test_a_logger_file_is_reduced_to_days_and_dry_downs():
    out = sensors_request({"csv": logger_csv(LEVELS)})
    assert out["readings"] == 36 * 8
    rec = out["records"][0]
    assert rec["device_id"] == "WL-1"
    assert len(rec["dry_downs"]) >= 2, "two deep drains reached the safe-AWD depth"
    assert {d["state"] for d in out["days"]} == {"flooded", "drained"}
    assert out["validation"] is None


def test_radar_calls_are_scored_against_the_logger():
    calls = [{"day": d.isoformat(), "state": "flooded" if lv > 0 else "drained",
              "p_flooded": 0.9 if lv > 0 else 0.1} for d, lv in LEVELS[::3]]
    out = sensors_request({"csv": logger_csv(LEVELS), "radar": calls})
    v = out["validation"]
    assert v["matched_passes"] == len(calls)
    assert v["accuracy"] == 1.0 and v["over_credit_errors"] == 0
    assert v["sufficient"] is False


def test_only_the_asked_plot_is_kept_and_the_rest_are_named():
    both = logger_csv(LEVELS, plot="farm-1") + "\n" + "\n".join(
        logger_csv(LEVELS, device="WL-2", plot="farm-2").splitlines()[1:])
    out = sensors_request({"csv": both, "plot_id": "farm-1"})
    assert [r["device_id"] for r in out["records"]] == ["WL-1"]
    assert out["other_plots"] == ["farm-2"]
    # A single-plot file under the logger's own id is taken as this farm's.
    solo = sensors_request({"csv": logger_csv(LEVELS, plot="L-17"), "plot_id": "farm-1"})
    assert solo["records"][0]["device_id"] == "WL-1"


@pytest.mark.parametrize("body,message", [
    ({}, "send the logger file"),
    ({"csv": "a,b\n1,2"}, "needs columns"),
    ({"csv": "device_id,plot_id,timestamp,water_level_cm\n"}, "no readings"),
    ({"csv": logger_csv(LEVELS[:2]), "radar": [{"day": "x"}]}, "radar call 1"),
])
def test_bad_logger_requests_say_what_to_fix(body, message):
    with pytest.raises(MonitoringError, match=message):
        sensors_request(body)


# --- scenes -------------------------------------------------------------------

class FakeStac:
    def __init__(self, days):
        self.days = days

    def fetch(self, connector, url, params=None, *, body=None, **_):
        feats = [{"id": f"S1A_{d.isoformat()}", "collection": "sentinel-1-grd",
                  "properties": {"datetime": f"{d.isoformat()}T00:42:10Z",
                                 "platform": "sentinel-1a", "sat:relative_orbit": 63,
                                 "sat:orbit_state": "descending"}}
                 for d in self.days]
        raw = json.dumps({"type": "FeatureCollection", "features": feats}).encode()
        return Snapshot(connector, url, (), "2026-10-29T00:00:00+00:00", "0" * 64, raw)


BOUNDARY = rice_request()["farm"]["boundary"]


def test_scenes_report_the_longest_gap():
    days = [date(2026, 6, 1) + timedelta(days=12 * i) for i in range(5)] + [date(2026, 8, 30)]
    out = scenes_request({"boundary": BOUNDARY, "start": "2026-06-01", "end": "2026-09-30"},
                         transport=FakeStac(days))
    assert out["scenes"] == 6 and out["usable_days"] == 6
    assert out["max_gap_days"] == 42
    assert out["scene_list"][0]["relative_orbit"] == 63


def test_an_unreachable_catalogue_is_a_clear_refusal():
    class Down:
        def fetch(self, connector, *a, **k):
            raise ConnectorUnavailable(connector, "offline in tests")
    with pytest.raises(MonitoringError, match="catalogue unavailable"):
        scenes_request({"boundary": BOUNDARY}, transport=Down())


@pytest.mark.parametrize("body,message", [
    ({"boundary": {"type": "Point"}}, "GeoJSON Polygon"),
    ({"boundary": BOUNDARY, "start": "2026-01-01", "end": "2025-01-01"}, "window"),
    ({"boundary": BOUNDARY, "sensor": "landsat"}, "sensor must be"),
])
def test_bad_scene_requests_say_what_to_fix(body, message):
    with pytest.raises(MonitoringError, match=message):
        scenes_request(body, transport=FakeStac([]))


# --- registry -----------------------------------------------------------------

EXPORT = """Issuance Date,Vintage Start,ID,Quantity Issued,Serial Number,Status
12/03/2026,01/01/2025,5123,9,VCS-5123-2025-000001-000009,Active
15/03/2026,01/01/2025,5123,4,VCS-5123-2025-000010-000013,Retired
"""


def test_our_issuances_reconcile_against_the_export():
    out = reconcile_request({"registry": "Verra", "csv": EXPORT, "issuances": [
        {"id": "v2025", "year": 2025, "quantity": 9, "registry_ref": "VCS-5123-2025-000001-000009"},
    ]})
    assert out["matched"] == 1 and out["matches"][0]["basis"] == "reference"
    assert out["clean"] is False, "the second registry row is not in our ledger"
    assert out["unknown_rows"][0]["quantity"] == 4
    assert out["retired_t"] == 4
    assert out["columns"]["quantity"] == "Quantity Issued"


def test_a_quantity_disagreement_is_a_finding():
    out = reconcile_request({"registry": "Verra", "csv": EXPORT, "issuances": [
        {"id": "v2025", "year": 2025, "quantity": 10, "registry_ref": "VCS-5123-2025-000001-000009"},
        {"id": "v2025b", "year": 2025, "quantity": 4},
    ]})
    assert out["disagreements"] == 1
    assert any("we issued 10" in f for f in out["findings"])
    assert any("vintage and quantity only" in f for f in out["findings"])


@pytest.mark.parametrize("body,message", [
    ({}, "registry export as csv"),
    ({"csv": "foo,bar\n1,2"}, "no column"),
    ({"csv": EXPORT, "issuances": [{"id": "x"}]}, "issuance 1"),
])
def test_bad_reconcile_requests_say_what_to_fix(body, message):
    with pytest.raises(MonitoringError, match=message):
        reconcile_request(body)


def test_the_routes_answer_422_on_bad_input():
    for path in ("/api/sensors", "/api/scenes", "/api/reconcile"):
        status, payload = dispatch(None, "POST", path, {}, {})
        assert status == 422 and payload["error"]
