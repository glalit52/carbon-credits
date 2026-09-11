import json

import pytest

from carbonstack import scenario, serialize
from carbonstack.cli import main
from carbonstack.domain import TenureBasis


def test_round_trip_preserves_everything_that_affects_credits(tmp_path):
    original = scenario.demo_estate(n_farmers=6)
    path = tmp_path / "p.json"
    serialize.save(original, path)
    restored = serialize.load(path)

    assert restored.id == original.id
    assert restored.track == original.track
    assert restored.area_ha == pytest.approx(original.area_ha)
    assert restored.creditable_area_ha() == pytest.approx(original.creditable_area_ha())
    assert restored.eligibility_issues() == original.eligibility_issues()
    assert {p.fingerprint for p in restored.plots.values()} == \
           {p.fingerprint for p in original.plots.values()}


def test_saved_document_is_readable_by_a_human(tmp_path):
    """A verifier opens this file in a text editor. Derived values are written
    alongside the raw ones so nothing has to be recomputed to be checked."""
    path = tmp_path / "p.json"
    serialize.save(scenario.demo_estate(n_farmers=3), path)
    payload = json.loads(path.read_text())

    assert payload["plots"][0]["area_ha"] > 0
    assert payload["plots"][0]["fingerprint"]
    assert payload["farmers"][0]["consent_reference"] is not None


def test_demo_scenarios_contain_the_awkward_rows():
    """A demo with clean data would teach the wrong lesson about what blocks
    an issuance."""
    estate = scenario.demo_estate()
    issues = estate.eligibility_issues()
    assert issues, "demo should contain blocked plots"
    flat = [m for problems in issues.values() for m in problems]
    assert any("tenure" in m for m in flat)
    assert any("consent" in m for m in flat)
    assert estate.creditable_area_ha() < estate.area_ha


def test_bridge_scenario_is_leasehold_rice():
    bridge = scenario.demo_bridge()
    assert all(p.tenure is TenureBasis.REGISTERED_LEASE for p in bridge.plots.values())
    assert {e.practice for e in bridge.enrollments} == {"awd"}


def test_cli_demo_runs(capsys):
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "VM0047" in out and "VM0042" in out
    assert "net issuable" in out


def test_cli_methodologies_lists_both(capsys):
    assert main(["methodologies"]) == 0
    out = capsys.readouterr().out
    assert "VM0047" in out and "VM0042" in out


def test_cli_export_then_eligibility(tmp_path, capsys):
    path = tmp_path / "p.json"
    assert main(["export", "estate", "--out", str(path)]) == 0
    capsys.readouterr()

    assert main(["eligibility", str(path)]) == 0
    out = capsys.readouterr().out
    assert "area lost to paperwork" in out
    assert "tenure basis is undocumented" in out


def test_cli_quantify_json_is_machine_readable(tmp_path, capsys):
    path = tmp_path / "p.json"
    main(["export", "estate", "--out", str(path)])
    capsys.readouterr()

    assert main(["quantify", str(path), "--year", "2031", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["methodology"] == "VM0047"
    assert payload["net_t"] > 0
    assert payload["calculations"]


def test_cli_explain_shows_the_derivation(tmp_path, capsys):
    path = tmp_path / "p.json"
    main(["export", "estate", "--out", str(path)])
    capsys.readouterr()

    assert main(["explain", str(path), "--year", "2031"]) == 0
    out = capsys.readouterr().out
    assert "Derivation" in out
    assert "above-ground biomass" in out
    assert "performance benchmark" in out
    assert "source:" in out


def test_cli_rejects_an_unknown_methodology(tmp_path):
    path = tmp_path / "p.json"
    main(["export", "estate", "--out", str(path)])
    with pytest.raises(KeyError):
        main(["quantify", str(path), "--year", "2031", "--methodology", "VM9999"])
