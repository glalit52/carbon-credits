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


def test_cli_export_then_import_and_eligibility(tmp_path, capsys):
    """The stateless export feeds the database import, and eligibility reads
    back out of it."""
    proj = tmp_path / "p.json"
    db = tmp_path / "t.db"
    assert main(["export", "estate", "--out", str(proj)]) == 0
    capsys.readouterr()

    assert main(["--db", str(db), "import", str(proj),
                 "--methodology", "VM0047"]) == 0
    capsys.readouterr()

    assert main(["--db", str(db), "eligibility", "AP-ARR-001"]) == 0
    out = capsys.readouterr().out
    assert "area lost to paperwork" in out
    assert "tenure basis is undocumented" in out


def test_cli_sites_lists_the_pilots(capsys):
    assert main(["sites"]) == 0
    out = capsys.readouterr().out
    assert "IN-TNJ-01" in out and "KE-NYR-01" in out
    assert "Thanjavur" in out and "Nyeri" in out


def test_cli_refuses_a_write_without_an_actor(tmp_path, capsys):
    """Every change to a commercial record is attributed, and the CLI says so
    rather than inventing a default."""
    db = tmp_path / "t.db"
    assert main(["--db", str(db), "enroll", "vallam"]) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        main(["--db", str(db), "review", "IN-TNJ-01:2025", "--approve"])
    assert "actor" in str(exc.value)


def test_cli_runs_the_whole_lifecycle(tmp_path, capsys):
    db = str(tmp_path / "t.db")

    assert main(["--db", db, "init"]) == 0
    assert main(["--db", db, "enroll", "vallam"]) == 0
    assert main(["--db", db, "monitor", "IN-TNJ-01", "--to", "2026-09-11"]) == 0
    assert main(["--db", db, "quantify", "IN-TNJ-01", "--year", "2025",
                 "--tier", "3", "--actor", "lalit"]) == 0
    capsys.readouterr()

    # Issuing before approval is refused, and the CLI exits non-zero.
    assert main(["--db", db, "issue", "IN-TNJ-01:2025",
                 "--registry", "Gold Standard", "--actor", "priya"]) == 2
    assert "refused" in capsys.readouterr().err

    assert main(["--db", db, "review", "IN-TNJ-01:2025", "--submit",
                 "--actor", "lalit"]) == 0
    assert main(["--db", db, "review", "IN-TNJ-01:2025", "--approve",
                 "--actor", "priya", "--note", "3 dry-downs confirmed"]) == 0
    assert main(["--db", db, "issue", "IN-TNJ-01:2025",
                 "--registry", "Gold Standard", "--actor", "priya"]) == 0
    assert main(["--db", db, "pay", "raise", "IN-TNJ-01:2025", "--price", "12",
                 "--share", "0.55", "--actor", "lalit"]) == 0
    capsys.readouterr()

    assert main(["--db", db, "verify"]) == 0
    assert "intact" in capsys.readouterr().out

    assert main(["--db", db, "evidence", "IN-TNJ-01",
                 "--out", str(tmp_path / "pack")]) == 0
    assert (tmp_path / "pack" / "SUMMARY.md").exists()


def test_cli_explain_reads_the_stored_derivation(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    main(["--db", db, "enroll", "vallam"])
    main(["--db", db, "monitor", "IN-TNJ-01", "--to", "2026-09-11"])
    main(["--db", db, "quantify", "IN-TNJ-01", "--year", "2025",
          "--actor", "lalit"])
    capsys.readouterr()

    assert main(["--db", db, "explain", "IN-TNJ-01:2025"]) == 0
    out = capsys.readouterr().out
    assert "VM0042 abatement" in out
    assert "source:" in out


def test_cli_verify_fails_loudly_on_a_tampered_database(tmp_path, capsys):
    import sqlite3

    db = str(tmp_path / "t.db")
    main(["--db", db, "enroll", "vallam"])
    capsys.readouterr()

    conn = sqlite3.connect(db)
    conn.execute("UPDATE events SET payload_json = '{}' WHERE id = 1")
    conn.commit()
    conn.close()

    assert main(["--db", db, "verify"]) == 1
    assert "BROKEN" in capsys.readouterr().err
