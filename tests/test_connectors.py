"""Connectors: outside data, and the pinning that makes it evidence.

No test here touches the network. Responses are built in the shape each
source documents and served through a fake or a replay transport -- which is
also exactly how a verifier re-runs our numbers.
"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from carbonstack.connectors.base import (
    ConnectorUnavailable, RecordingTransport, ReplayTransport, Snapshot, pin,
    request_key,
)
from carbonstack.connectors import registry, sensors, soilgrids, stac, weather
from carbonstack.ledger import Issuance
from carbonstack.sar import Classification, WaterState


class FakeTransport:
    """Serves canned bodies by connector name and records what was asked."""

    def __init__(self, bodies):
        self.bodies = bodies
        self.calls = []

    def fetch(self, connector, url, params=None, *, body=None):
        self.calls.append((connector, url, params, body))
        payload = self.bodies[connector]
        if callable(payload):
            payload = payload(body)
        raw = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
        import hashlib
        return Snapshot(connector, url,
                        tuple(sorted((k, str(v)) for k, v in (params or {}).items())),
                        "2026-10-22T00:00:00+00:00", hashlib.sha256(raw).hexdigest(), raw)


# --- pinning ------------------------------------------------------------------

def test_request_key_ignores_parameter_order_and_type():
    a = request_key("u", {"lat": 10.5, "lon": 79})
    b = request_key("u", {"lon": "79", "lat": "10.5"})
    assert a == b


def test_a_pinned_response_replays_byte_for_byte(tmp_path):
    live = FakeTransport({"open-meteo": {"daily": {"time": []}}})
    rec = RecordingTransport(live, tmp_path)
    first = rec.fetch("open-meteo", "https://x", {"a": 1})
    again = ReplayTransport(tmp_path).fetch("open-meteo", "https://x", {"a": 1})
    assert again.sha256 == first.sha256
    assert again.replayed and not first.replayed


def test_an_edited_pinned_response_is_refused(tmp_path):
    """Pinning exists to catch exactly this."""
    snap = FakeTransport({"c": {"v": 1}}).fetch("c", "https://x", {})
    path = pin(tmp_path, snap)
    rec = json.loads(path.read_text())
    rec["body"] = rec["body"].replace("1", "2")
    path.write_text(json.dumps(rec))
    with pytest.raises(ConnectorUnavailable, match="does not match its hash"):
        ReplayTransport(tmp_path).fetch("c", "https://x", {})


def test_missing_replay_says_how_to_fix_it(tmp_path):
    with pytest.raises(ConnectorUnavailable, match="--record"):
        ReplayTransport(tmp_path).fetch("c", "https://x", {"q": 1})


# --- weather ------------------------------------------------------------------

def _open_meteo_body(start, days, *, drop=None):
    times, t, r, e = [], [], [], []
    for i in range(days):
        d = start + timedelta(days=i)
        times.append(d.isoformat())
        t.append(None if d == drop else 25.0 + (d.month % 3))
        r.append(4.0)
        e.append(5.0)
    return {"daily": {"time": times, "temperature_2m_mean": t,
                      "precipitation_sum": r, "et0_fao_evapotranspiration": e}}


def test_open_meteo_aggregates_whole_months_and_drops_partial_ones():
    body = _open_meteo_body(date(2024, 1, 1), 366, drop=date(2024, 3, 9))
    series = weather.open_meteo(FakeTransport({"open-meteo": body}),
                                10.78, 79.13, date(2024, 1, 1), date(2024, 12, 31))
    assert len(series.months) == 11                 # March had a hole
    jan = series.months[0]
    assert jan.rain_mm == pytest.approx(124.0)      # 31 days x 4 mm
    assert jan.pet_method == "fao56"
    assert series.provenance[0]["sha256"]


def test_normals_refuse_a_missing_calendar_month():
    body = _open_meteo_body(date(2024, 1, 1), 366, drop=date(2024, 3, 9))
    series = weather.open_meteo(FakeTransport({"open-meteo": body}),
                                10.78, 79.13, date(2024, 1, 1), date(2024, 12, 31))
    with pytest.raises(ValueError, match="Mar"):
        series.normals()


def test_nasa_power_converts_daily_rate_to_monthly_total_and_skips_annual():
    t2m = {f"2023{m:02d}": 26.0 for m in range(1, 13)} | {"202313": 26.0}
    pr = {f"2023{m:02d}": 2.0 for m in range(1, 13)} | {"202313": 2.0}
    body = {"properties": {"parameter": {"T2M": t2m, "PRECTOTCORR": pr}}}
    series = weather.nasa_power(FakeTransport({"nasa-power": body}), 10.8, 79.1, 2023, 2023)
    assert len(series.months) == 12
    assert series.months[1].rain_mm == pytest.approx(56.0)   # Feb 2023: 28 days
    assert all(m.pet_method == "thornthwaite" for m in series.months)


def test_thornthwaite_is_larger_in_the_warm_season():
    temps = [5, 6, 9, 12, 15, 18, 20, 19, 16, 12, 8, 5]
    pet = weather.thornthwaite_pet(temps, 52.0)
    assert pet.index(max(pet)) in (5, 6)
    assert pet[0] < 15


# --- soilgrids ----------------------------------------------------------------

def _soilgrids_body(clay=(350, 360, 380), soc=(120, 90, 70), bdod=(130, 140, 145)):
    labels = [("0-5cm", 0, 5), ("5-15cm", 5, 15), ("15-30cm", 15, 30)]

    def layer(name, d_factor, vals, spread=0.4):
        return {"name": name, "unit_measure": {"d_factor": d_factor},
                "depths": [{"label": lab, "range": {"top_depth": a, "bottom_depth": b},
                            "values": {"mean": v, "Q0.05": v * (1 - spread),
                                       "Q0.95": v * (1 + spread)}}
                           for (lab, a, b), v in zip(labels, vals)]}
    return {"properties": {"layers": [
        layer("clay", 10, clay), layer("soc", 10, soc),
        layer("bdod", 100, bdod), layer("cfvo", 10, (20, 20, 30)),
    ]}}


def test_soilgrids_applies_each_layers_own_d_factor():
    prior = soilgrids.soilgrids(FakeTransport({"soilgrids": _soilgrids_body()}), 10.78, 79.13)
    assert prior.clay_pct == pytest.approx((35 * 5 + 36 * 10 + 38 * 15) / 30)
    top = prior.layers[0]
    assert top.soc_g_kg == pytest.approx(12.0)
    assert top.bulk_density_g_cm3 == pytest.approx(1.30)
    # 1.2% C x 1.30 x 5 cm x 100 x (1 - 0.02) = 7.64 t C/ha in the top layer
    assert 25 < prior.soc_t_ha() < 45


def test_soilgrids_reports_its_interval_and_refuses_to_be_a_baseline():
    prior = soilgrids.soilgrids(FakeTransport({"soilgrids": _soilgrids_body()}), 10.78, 79.13)
    lo, hi = prior.soc_interval_t_ha()
    assert lo < prior.soc_t_ha() < hi
    with pytest.raises(ValueError, match="not a measured baseline"):
        prior.as_baseline()


def test_soilgrids_null_over_water_is_unavailable_not_zero():
    body = _soilgrids_body()
    body["properties"]["layers"][1]["depths"][0]["values"]["mean"] = None
    with pytest.raises(ConnectorUnavailable, match="water or built-up"):
        soilgrids.soilgrids(FakeTransport({"soilgrids": body}), 10.0, 79.0)


# --- stac ---------------------------------------------------------------------

def _features(days, cloud=None, nxt=None):
    feats = [{"id": f"S1_{d.isoformat()}", "collection": "sentinel-1-grd",
              "properties": {"datetime": f"{d.isoformat()}T00:42:10Z",
                             "platform": "sentinel-1a",
                             **({"eo:cloud_cover": cloud(d)} if cloud else {})}}
             for d in days]
    links = [{"rel": "next", "body": {"next": nxt}}] if nxt else []
    return {"type": "FeatureCollection", "features": feats, "links": links}


def test_stac_follows_pagination_and_measures_the_longest_gap():
    start = date(2025, 6, 10)
    page1 = [start + timedelta(days=12 * i) for i in range(4)]
    page2 = [page1[-1] + timedelta(days=24), page1[-1] + timedelta(days=36)]

    def respond(body):
        return _features(page2) if body.get("next") else _features(page1, nxt="tok")

    t = FakeTransport({"stac": respond})
    cov = stac.search(t, bbox=[79.1, 10.7, 79.2, 10.8], start=start,
                      end=page2[-1] + timedelta(days=6), sensor="s1")
    assert len(t.calls) == 2
    assert len(cov.usable_days) == 6
    assert cov.max_gap_days == 24
    assert cov.median_revisit_days == 12.0
    assert not cov.can_resolve(event_days=14)


def test_a_blind_spot_at_the_end_of_the_window_counts_as_a_gap():
    start = date(2025, 6, 10)
    t = FakeTransport({"stac": _features([start + timedelta(days=6 * i) for i in range(5)])})
    cov = stac.search(t, bbox=[0, 0, 1, 1], start=start, end=start + timedelta(days=60))
    assert cov.max_gap_days == 36


def test_stac_counts_only_clear_optical_passes():
    days = [date(2025, 7, 1) + timedelta(days=5 * i) for i in range(10)]
    t = FakeTransport({"stac": _features(days, cloud=lambda d: 80 if d.day % 2 else 10)})
    cov = stac.search(t, bbox=[0, 0, 1, 1], start=days[0], end=days[-1], sensor="s2")
    assert len(cov.acquisition_days) == 10
    assert len(cov.usable_days) < 10


def test_stac_refuses_to_return_a_truncated_list():
    t = FakeTransport({"stac": lambda body: _features([date(2025, 1, 1)], nxt="again")})
    with pytest.raises(ConnectorUnavailable, match="understate"):
        stac.search(t, bbox=[0, 0, 1, 1], start=date(2025, 1, 1),
                    end=date(2025, 2, 1), max_pages=3)


# --- sensors --------------------------------------------------------------------

def _logger_csv(levels_by_day, device="WL-01", plot="IN-TNJ-01-P1", per_day=6):
    lines = ["device_id,plot_id,timestamp,water_level_cm"]
    for d, level in levels_by_day:
        for h in range(per_day):
            at = datetime(d.year, d.month, d.day, h * 4, tzinfo=timezone.utc)
            # small movement so a real record is never a flatline
            lines.append(f"{device},{plot},{at.isoformat()},{level + 0.1 * (h % 2):.2f}")
    return "\n".join(lines)


def test_logger_days_are_classified_with_a_dead_band():
    start = date(2025, 7, 1)
    levels = [(start + timedelta(days=i), lv) for i, lv in
              enumerate([5, 5, 5, -1, -8, -18, -20, 4, 5])]
    rec = sensors.clean(sensors.parse_csv(_logger_csv(levels)))[0]
    states = [d.state for d in rec.days]
    assert states[3] is WaterState.AMBIGUOUS          # -1 cm: neither
    assert states[5] is WaterState.DRAINED
    events = rec.dry_downs()
    assert len(events) == 1 and events[0][2] <= -18


def test_a_shallow_dry_spell_is_not_an_awd_event():
    start = date(2025, 7, 1)
    levels = [(start + timedelta(days=i), lv) for i, lv in enumerate([5, -7, -8, 5])]
    rec = sensors.clean(sensors.parse_csv(_logger_csv(levels)))[0]
    assert rec.dry_downs() == []


def test_spikes_and_flatlines_are_removed_and_reported():
    t0 = datetime(2025, 7, 1, tzinfo=timezone.utc)
    rows = ["device_id,plot_id,timestamp,water_level_cm"]
    for h in range(0, 24 * 5):
        level = 3.0                                         # stuck for five days
        if h == 30:
            level = 40.0                                    # a frog
        rows.append(f"WL-9,P1,{(t0 + timedelta(hours=h)).isoformat()},{level}")
    rec = sensors.clean(sensors.parse_csv("\n".join(rows)))[0]
    assert rec.dropped_spikes == 1
    assert rec.flatline_hours >= 72
    assert any("silting" in i for i in rec.issues)


def test_json_webhook_batches_parse():
    payload = json.dumps([{"device_id": "WL-1", "plot_id": "P1", "readings": [
        {"t": "2025-07-01T00:00:00Z", "level_cm": 4.2},
        {"t": "2025-07-01T06:00:00Z", "level_cm": None}]}])
    assert len(sensors.parse_json(payload)) == 1


def _call(d, state, p):
    return Classification(day=d, state=state, p_flooded=p, stage_estimate=0.3,
                          separation_db=3.0, vv_normalised_db=-15.0)


def test_detector_is_scored_against_measured_water_and_loggers_that_disagree_are_dropped():
    start = date(2025, 7, 1)
    levels = [(start + timedelta(days=i), 5 if i % 6 < 3 else -12) for i in range(36)]
    a = sensors.clean(sensors.parse_csv(_logger_csv(levels, device="A")))[0]
    # B agrees except on day 0
    levels_b = [(d, (-12 if i == 0 else lv)) for i, (d, lv) in enumerate(levels)]
    b = sensors.clean(sensors.parse_csv(_logger_csv(levels_b, device="B")))[0]
    calls = []
    for i in range(0, 36, 2):
        d = start + timedelta(days=i)
        flooded = i % 6 < 3
        calls.append(_call(d, WaterState.FLOODED if flooded else WaterState.DRAINED,
                           0.9 if flooded else 0.1))
    v = sensors.validate_detector(calls, [a, b])
    assert v.unmatched_passes == 1                    # day 0 is contested
    assert v.result["accuracy"] == 1.0
    assert v.over_credit_errors == 0
    assert not v.sufficient                           # 17 passes is not 30


# --- registry -----------------------------------------------------------------

VERRA_LIKE = """Issuance Date,Vintage Start,Vintage End,ID,Name,Quantity Issued,Serial Number,Retirement/Cancellation Date,Total Vintage Quantity
12/03/2026,01/01/2025,31/12/2025,5123,Vallam AWD,2,IN-TNJ-01-2025-00000001 to IN-TNJ-01-2025-00000002,,2
15/03/2026,01/01/2025,31/12/2025,5123,Vallam AWD,7,9900-123-001-007,,7
"""


def _iss(vid, qty, start, ref=""):
    return Issuance(id=f"iss-{vid}", vintage_id=vid, quantity=qty,
                    serial_start=start, serial_end=start, issued_on=date(2026, 3, 12),
                    registry="Verra", registry_ref=ref)


def test_registry_columns_are_found_by_alias_and_reported():
    exp = registry.parse_export(VERRA_LIKE, registry="Verra")
    assert exp.columns["quantity"] == "Quantity Issued"     # not the vintage total
    assert exp.columns["serial"] == "Serial Number"
    assert exp.rows[0].vintage == 2025


def test_reconciliation_finds_both_sides_of_a_disagreement():
    exp = registry.parse_export(VERRA_LIKE, registry="Verra")
    ours = [_iss("IN-TNJ-01:2025", 2, "IN-TNJ-01-2025-00000001"),
            _iss("IN-TNJ-01:2026", 1, "IN-TNJ-01-2026-00000001")]
    rec = registry.reconcile(ours, exp)
    assert rec.matches[0].basis == "serial" and rec.matches[0].agrees
    assert [i.id for i in rec.missing_at_registry] == ["iss-IN-TNJ-01:2026"]
    assert [r.line for r in rec.unknown_to_us] == [3]
    assert not rec.clean
    assert any("no issuance in our ledger" in f for f in rec.findings())


def test_an_export_without_a_quantity_column_fails_at_the_header():
    with pytest.raises(ValueError, match="quantity"):
        registry.parse_export("Vintage,Name\n2025,x\n", registry="Gold Standard")
