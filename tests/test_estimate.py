"""Estimates for farms the engine has never seen: a polygon and a calendar in,
creditable and potential tonnes out, with every generic input named."""

import hashlib
import importlib.util
import io
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from carbonstack.api import dispatch
from carbonstack.connectors.base import ConnectorUnavailable, Snapshot
from carbonstack.estimate import EstimateError, build_site, estimate
from carbonstack.sites import NYERI, THANJAVUR

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 29)

KURUVAI = {"name": "Kuruvai", "start_month": 6, "start_day": 10, "end_month": 9, "end_day": 25}
SAMBA = {"name": "Samba", "start_month": 8, "start_day": 20, "end_month": 1, "end_day": 20}


def polygon(site):
    ring = [list(p) for p in site.boundary]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


def normals(site):
    return {"monthly_rain_mm": list(site.climate.monthly_rain_mm),
            "mean_temp_c": site.climate.mean_temp_c,
            "temp_amplitude_c": site.climate.temp_amplitude_c}


def rice_request(**farm):
    base = {"pathway": "rice", "boundary": polygon(THANJAVUR), "enrolled_on": "2025-06-01",
            "seasons": [KURUVAI, SAMBA], "rice_ecosystem": "irrigated_lowland",
            "water_control": "full", "tenure": "owned_title",
            "tenure_reference": "TN/RoR/THJ/2016/04412"}
    return {"farm": {**base, **farm}, "climate_source": "normals",
            "climate_normals": normals(THANJAVUR)}


def tree_request(**farm):
    base = {"pathway": "agroforestry", "boundary": polygon(NYERI), "enrolled_on": "2025-03-20",
            "tenure": "owned_title", "tenure_reference": "KE/LR/NYERI/8841",
            "species": ["Grevillea robusta"]}
    return {"farm": {**base, **farm}, "climate_source": "normals",
            "climate_normals": normals(NYERI)}


class NoNetwork:
    def fetch(self, connector, url, params=None, **_):
        raise ConnectorUnavailable(connector, "offline in tests")


class FakeOpenMeteo:
    """Answers Open-Meteo with ten flat years: 4 mm/day, 27 C."""

    def __init__(self):
        self.calls = []

    def fetch(self, connector, url, params=None, **_):
        self.calls.append((connector, params))
        if connector != "open-meteo":
            raise ConnectorUnavailable(connector, "not faked")
        start = date.fromisoformat(params["start_date"])
        end = date.fromisoformat(params["end_date"])
        days = (end - start).days + 1
        body = json.dumps({"daily": {
            "time": [(start + timedelta(days=i)).isoformat() for i in range(days)],
            "temperature_2m_mean": [27.0] * days,
            "precipitation_sum": [4.0] * days,
            "et0_fao_evapotranspiration": [4.5] * days}}).encode()
        return Snapshot(connector, url, tuple(sorted(params.items())),
                        "2026-10-29T00:00:00+00:00", hashlib.sha256(body).hexdigest(), body)


def test_a_documented_rice_farm_is_creditable_now():
    out = estimate(rice_request(), transport=NoNetwork(), today=TODAY)
    assert out["methodology"] == "VM0051"
    assert out["blockers"] == []
    assert out["totals"]["creditable_net_t"] > 0
    assert out["totals"]["creditable_net_t"] == out["totals"]["potential_net_t"]
    assert {v["year"] for v in out["vintages"]} == {2025, 2026}
    assert out["seasons"], "rice estimates carry their season summaries"


def test_missing_paperwork_blocks_credits_but_not_potential():
    """Without a tenure document the verifier excludes the plot. The estimate
    says so, and still shows what completing the paperwork would unlock."""
    out = estimate(rice_request(tenure_reference=None), transport=NoNetwork(), today=TODAY)
    assert out["totals"]["creditable_net_t"] == 0
    assert out["totals"]["potential_net_t"] > 0
    assert any("reference document" in b for b in out["blockers"])


def test_physical_ineligibility_is_not_assumed_away():
    """Rainfed rice is outside VM0051. Paperwork cannot fix that, so the
    potential is zero too."""
    out = estimate(rice_request(rice_ecosystem="rainfed"), transport=NoNetwork(), today=TODAY)
    assert out["totals"]["potential_net_t"] == 0
    assert any("rainfed" in b for b in out["blockers"])


def test_generic_inputs_are_named_as_assumptions():
    out = estimate(rice_request(), transport=NoNetwork(), today=TODAY)
    named = {a["parameter"] for a in out["site"]["assumptions"]}
    assert {"baseline_ch4_kg_ha_season", "awd_reduction"} <= named
    assert any("IPCC 2019" in a["basis"] for a in out["site"]["assumptions"])

    given = rice_request(parameters={"baseline_ch4_kg_ha_season": 78.0, "awd_reduction": 0.42})
    out = estimate(given, transport=NoNetwork(), today=TODAY)
    assert out["site"]["assumptions"] == []


def test_a_higher_baseline_earns_more():
    low = estimate(rice_request(parameters={"baseline_ch4_kg_ha_season": 60.0}),
                   transport=NoNetwork(), today=TODAY)
    high = estimate(rice_request(parameters={"baseline_ch4_kg_ha_season": 120.0}),
                    transport=NoNetwork(), today=TODAY)
    assert high["totals"]["potential_net_t"] > low["totals"]["potential_net_t"]


def test_agroforestry_grows_year_on_year():
    out = estimate(tree_request(enrolled_on="2022-03-01"), transport=NoNetwork(), today=TODAY)
    nets = [v["net_t"] for v in out["vintages"]]
    assert out["methodology"] == "VM0047"
    assert len(nets) == 5 and nets[-1] > nets[0]


def test_the_current_year_is_labelled_a_projection():
    out = estimate(rice_request(), transport=NoNetwork(), today=TODAY)
    current = next(v for v in out["vintages"] if v["year"] == TODAY.year)
    assert any("projection" in w for w in current["warnings"])


def test_live_climate_is_used_when_reachable_and_recorded():
    fake = FakeOpenMeteo()
    req = rice_request()
    req.pop("climate_normals")
    req["climate_source"] = "auto"
    site, record = build_site(req, transport=fake, today=TODAY)
    assert fake.calls[0][1]["start_date"] == "2016-01-01"
    assert fake.calls[0][1]["end_date"] == "2025-12-31"
    assert record["climate"]["quality"] == "measured"
    assert record["climate"]["source"].startswith("Open-Meteo")
    assert record["climate"]["provenance"], "the fetch is pinned in the record"
    assert site.climate.monthly_rain_mm[0] == pytest.approx(124.0)   # 31 days x 4 mm
    assert site.climate.mean_temp_c == pytest.approx(27.0)


def test_a_farm_with_no_climate_is_refused_not_guessed():
    req = rice_request()
    req.pop("climate_normals")
    req["climate_source"] = "auto"
    with pytest.raises(EstimateError, match="no climate for this location"):
        estimate(req, transport=NoNetwork(), today=TODAY)


@pytest.mark.parametrize("change,message", [
    ({"pathway": "biochar"}, "pathway must be one of"),
    ({"boundary": {"type": "Point", "coordinates": [0, 0]}}, "not a polygon"),
    ({"boundary": {"type": "Polygon", "coordinates": [[[0, 0], [0, 0], [0, 0]]]}}, "boundary"),
    ({"seasons": []}, "crop calendar"),
    ({"seasons": [{"start_month": 13, "end_month": 2}]}, "valid month"),
    ({"enrolled_on": "2030-01-01"}, "future"),
    ({"tenure": "squatting"}, "tenure"),
])
def test_bad_requests_say_what_to_fix(change, message):
    with pytest.raises(EstimateError, match=message):
        estimate(rice_request(**change), transport=NoNetwork(), today=TODAY)


def test_multipolygon_uses_its_largest_part():
    big = polygon(THANJAVUR)["coordinates"]
    lon, lat = THANJAVUR.boundary[0]
    sliver = [[[lon + 1, lat], [lon + 1.0003, lat], [lon + 1.0003, lat + 0.0003], [lon + 1, lat]]]
    site, record = build_site(rice_request(boundary={"type": "MultiPolygon",
                                                     "coordinates": [sliver, big]}),
                              transport=NoNetwork(), today=TODAY)
    assert record["area_ha"] == round(THANJAVUR.area_ha, 4)


def test_the_api_route_maps_bad_input_to_422():
    status, payload = dispatch(None, "POST", "/api/estimate", {}, {"farm": {"pathway": "x"}})
    assert status == 422
    assert "pathway" in payload["error"]


# ---------------------------------------------------------------------------
# The Vercel adapter: one stateless POST, behind a token
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def adapter():
    spec = importlib.util.spec_from_file_location("vercel_api_estimate", ROOT / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def post(adapter, path, body, *, auth=None):
    raw = json.dumps(body).encode() if not isinstance(body, bytes) else body

    class Probe(adapter.handler):
        def __init__(self):            # no socket: drive the methods directly
            self.path = "/api/index?p=" + path.removeprefix("/api/")
            self.headers = {"Content-Length": str(len(raw))}
            if auth:
                self.headers["Authorization"] = auth
            self.rfile = io.BytesIO(raw)
            self.sent = None

        def _send(self, status, payload, *, cache=True):
            self.sent = (status, payload, cache)

    probe = Probe()
    probe.do_POST()
    return probe.sent


def test_other_writes_are_still_refused(adapter, monkeypatch):
    monkeypatch.setenv("CARBONSTACK_ENGINE_TOKEN", "s3cret")
    status, payload, _ = post(adapter, "/api/vintages/IN-TNJ-01:2025/approve", {},
                              auth="Bearer s3cret")
    assert status == 503 and "read-only" in payload["error"]


def test_estimates_are_off_until_a_token_is_configured(adapter, monkeypatch):
    monkeypatch.delenv("CARBONSTACK_ENGINE_TOKEN", raising=False)
    status, payload, _ = post(adapter, "/api/estimate", rice_request())
    assert status == 503 and "CARBONSTACK_ENGINE_TOKEN" in payload["fix"]


def test_estimates_need_the_token(adapter, monkeypatch):
    monkeypatch.setenv("CARBONSTACK_ENGINE_TOKEN", "s3cret")
    assert post(adapter, "/api/estimate", rice_request())[0] == 401
    assert post(adapter, "/api/estimate", rice_request(), auth="Bearer wrong")[0] == 401


def test_an_authorised_estimate_runs_and_is_not_cached(adapter, monkeypatch):
    monkeypatch.setenv("CARBONSTACK_ENGINE_TOKEN", "s3cret")
    status, payload, cache = post(adapter, "/api/estimate", rice_request(),
                                  auth="Bearer s3cret")
    assert status == 200, payload
    assert payload["totals"]["creditable_net_t"] > 0
    assert cache is False


def test_garbage_bodies_are_rejected(adapter, monkeypatch):
    monkeypatch.setenv("CARBONSTACK_ENGINE_TOKEN", "s3cret")
    assert post(adapter, "/api/estimate", b"{not json", auth="Bearer s3cret")[0] == 400
