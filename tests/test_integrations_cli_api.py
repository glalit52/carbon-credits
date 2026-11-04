"""The integration commands and endpoints, run the way a verifier would:
from pinned responses, with no network."""

import hashlib
import json
from datetime import date, timedelta

import pytest

from carbonstack.api import dispatch
from carbonstack.cli import main
from carbonstack.connectors.base import Snapshot, pin
from carbonstack.connectors.weather import OPEN_METEO_DAILY, OPEN_METEO_URL
from carbonstack.sites import THANJAVUR


def _pin_open_meteo(root, start, end):
    days = (end - start).days + 1
    body = {"daily": {
        "time": [(start + timedelta(days=i)).isoformat() for i in range(days)],
        "temperature_2m_mean": [28.0] * days,
        "precipitation_sum": [3.0] * days,
        "et0_fao_evapotranspiration": [4.5] * days}}
    raw = json.dumps(body).encode()
    params = {"latitude": f"{THANJAVUR.lat:.4f}", "longitude": f"{THANJAVUR.lon:.4f}",
              "start_date": start.isoformat(), "end_date": end.isoformat(),
              "daily": OPEN_METEO_DAILY, "timezone": "UTC"}
    pin(root, Snapshot("open-meteo", OPEN_METEO_URL, tuple(sorted(params.items())),
                       "2026-10-22T00:00:00+00:00", hashlib.sha256(raw).hexdigest(), raw))


def test_climate_replays_from_pinned_responses(tmp_path, capsys):
    _pin_open_meteo(tmp_path, date(2024, 1, 1), date(2024, 12, 31))
    assert main(["data", "climate", "vallam", "--source", "open-meteo",
                 "--from", "2024-01-01", "--to", "2024-12-31",
                 "--replay", str(tmp_path), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["months"]) == 12
    assert out["provenance"][0]["replayed"] is True


def test_soc_projection_runs_on_replayed_weather(tmp_path, capsys):
    _pin_open_meteo(tmp_path, date(2024, 1, 1), date(2024, 12, 31))
    assert main(["soc", "project", "vallam", "--source", "open-meteo",
                 "--from", "2024-01-01", "--to", "2024-12-31", "--replay", str(tmp_path),
                 "--clay", "38", "--soc", "32", "--practice", "residue_retention",
                 "--horizon", "5", "--draws", "20", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["delta_t_c_ha"][-1] > 0
    assert any("Shirato" in w for w in out["warnings"])     # paddy months detected


def test_soc_without_soil_inputs_asks_for_cores():
    with pytest.raises(SystemExit, match="--clay and --soc"):
        main(["soc", "project", "gatugi", "--practice", "cover_crop"])


def test_missing_replay_is_reported_not_defaulted(tmp_path):
    with pytest.raises(SystemExit, match="unavailable"):
        main(["data", "soil", "vallam", "--replay", str(tmp_path)])


def test_standards_compare_cli(capsys):
    assert main(["standards", "compare", "--pathway", "rice", "--gross", "100",
                 "--uncertainty", "0.2", "--country", "India", "--vintage", "2026",
                 "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["routes"][0]["route"] == "vcs-vm0051"


def test_sensor_ingest_cli(tmp_path, capsys):
    f = tmp_path / "loggers.csv"
    rows = ["device_id,plot_id,timestamp,water_level_cm"]
    for d in range(10):
        for h in range(6):
            lv = 5 if d < 4 or d > 7 else -18
            rows.append(f"WL-1,IN-TNJ-01-P1,2025-07-{d + 1:02d}T{h * 4:02d}:00:00Z,"
                        f"{lv + 0.1 * (h % 2)}")
    f.write_text("\n".join(rows))
    assert main(["sensors", "ingest", str(f), "--json"]) == 0
    rec = json.loads(capsys.readouterr().out)[0]
    assert len(rec["dry_downs"]) == 1


def test_registry_reconcile_cli_exits_nonzero_when_unclean(tmp_path, capsys):
    f = tmp_path / "export.csv"
    f.write_text("Vintage,Quantity Issued,Serial Number\n2025,3,X-2025-00000001\n")
    db = tmp_path / "c.db"
    assert main(["--db", str(db), "init"]) == 0
    assert main(["--db", str(db), "registry", "reconcile", str(f),
                 "--registry", "Verra"]) == 1
    assert "no issuance in our ledger" in capsys.readouterr().out


def test_api_standards_and_soc():
    status, body = dispatch(None, "GET", "/api/standards", {"pathway": ["biochar"]}, {})
    assert status == 200 and {r["id"] for r in body["routes"]} >= {"puro-biochar"}
    status, body = dispatch(None, "GET", "/api/sites/KE-NYR-01/soc",
                            {"clay": ["45"], "soc": ["55"], "practice": ["cover_crop"],
                             "draws": ["10"], "horizon": ["5"]}, {})
    assert status == 200 and body["delta_t_c_ha"][-1] > 0
    status, _ = dispatch(None, "GET", "/api/standards/compare", {"pathway": ["rice"]}, {})
    assert status == 400
