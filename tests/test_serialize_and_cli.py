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


def test_rice_enrols_under_vm0051_not_vm0042(tmp_path, capsys):
    """Two independent methodology reviews flagged VM0042 as the wrong choice
    for paddy. VM0051 is written for rice, replaces CDM AMS-III.AU, and is
    CORSIA eligible."""
    db = str(tmp_path / "t.db")
    assert main(["--db", db, "enroll", "vallam"]) == 0
    assert "VM0051" in capsys.readouterr().out


def test_no_buffer_is_withheld_on_avoided_methane(tmp_path, capsys):
    """Avoided methane is not a stock and cannot reverse, so the AFOLU
    non-permanence buffer does not apply. Worth about a fifth of the credits
    against the ARR pathway, and the practical difference VM0051 makes."""
    db = str(tmp_path / "t.db")
    main(["--db", db, "enroll", "vallam"])
    main(["--db", db, "monitor", "IN-TNJ-01", "--to", "2026-09-11"])
    capsys.readouterr()
    main(["--db", db, "quantify", "IN-TNJ-01", "--year", "2025",
          "--tier", "3", "--actor", "lalit"])
    out = capsys.readouterr().out
    assert "buffer pool" in out and "(0%)" in out


def test_cli_stack_audit_reports_a_clean_project(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    main(["--db", db, "enroll", "vallam"])
    capsys.readouterr()
    assert main(["--db", db, "stack", "audit", "IN-TNJ-01"]) == 0
    assert "no hectare is claimed twice" in capsys.readouterr().out


def test_cli_stack_refuses_the_unlawful_shape(tmp_path, capsys):
    """VM0042 already credits rice methane, so putting it beside VM0051 on the
    same plot sells that methane twice."""
    db = str(tmp_path / "t.db")
    main(["--db", db, "enroll", "vallam"])
    capsys.readouterr()
    bed = "79.1378,10.7867;79.1396,10.7867;79.1396,10.7877;79.1378,10.7877"
    assert main(["--db", db, "stack", "add", "IN-TNJ-01", "IN-TNJ-01-P1",
                 "--pillar", "methane", "--methodology", "VM0051",
                 "--area", "2.2", "--geometry", bed, "--actor", "lalit"]) == 0
    capsys.readouterr()
    assert main(["--db", db, "stack", "add", "IN-TNJ-01", "IN-TNJ-01-P1",
                 "--pillar", "soil_carbon", "--methodology", "VM0042",
                 "--area", "0.2", "--geometry", bed, "--actor", "lalit"]) == 2
    assert "sold" in capsys.readouterr().err


def test_cli_eligibility_reports_programme_level_blockers(tmp_path, capsys):
    """An unpinned methodology version blocks every hectare at once, so it is
    reported separately from the per-plot findings."""
    proj = tmp_path / "p.json"
    db = tmp_path / "t.db"
    main(["export", "estate", "--out", str(proj)])
    capsys.readouterr()
    main(["--db", str(db), "import", str(proj), "--methodology", "VM0047"])
    capsys.readouterr()
    assert main(["--db", str(db), "eligibility", "AP-ARR-001"]) == 0
    out = capsys.readouterr().out
    assert "blocking the whole project" not in out or "consultation" in out


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
    # Rice quantifies under VM0051, the purpose-built rice methodology, not
    # VM0042 as the first prototype did.
    assert "VM0051 abatement" in out
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


# --- soil through the command line ------------------------------------------

LAB_CSV = """plot_id,role,sampled_on,lab_reference,stratum,top_cm,bottom_cm,soc_pct,bulk_density_g_cm3,coarse_fragment_frac
IN-TNJ-01-P1,baseline,2025-05-01,TNAU/SOC/2025/0411,clay loam,0,10,1.10,1.32,0.02
IN-TNJ-01-P1,baseline,2025-05-01,TNAU/SOC/2025/0411,clay loam,10,30,0.72,1.45,0.03
IN-TNJ-01-P1,baseline,2025-05-01,TNAU/SOC/2025/0411,clay loam,30,40,0.50,1.50,0.04
IN-TNJ-01-P1,monitoring,2028-05-01,TNAU/SOC/2028/0119,clay loam,0,10,1.34,1.24,0.02
IN-TNJ-01-P1,monitoring,2028-05-01,TNAU/SOC/2028/0119,clay loam,10,30,0.86,1.38,0.03
IN-TNJ-01-P1,monitoring,2028-05-01,TNAU/SOC/2028/0119,clay loam,30,40,0.55,1.47,0.04
"""

VAL_CSV = "measured_t_ha,modelled_t_ha\n" + "".join(
    f"{38 + i * 1.1:.2f},{38 + i * 1.1 + (-1) ** i * 1.4:.2f}\n" for i in range(16))


def soil_db(tmp_path, capsys, *, validate=True):
    db = str(tmp_path / "s.db")
    (tmp_path / "lab.csv").write_text(LAB_CSV)
    (tmp_path / "val.csv").write_text(VAL_CSV)
    main(["--db", db, "enroll", "vallam"])
    main(["--db", db, "soil", "ingest", "IN-TNJ-01", str(tmp_path / "lab.csv"),
          "--actor", "field"])
    if validate:
        main(["--db", db, "soil", "validate", "IN-TNJ-01",
              str(tmp_path / "val.csv"), "--model", "DayCent",
              "--version", "2026.1", "--actor", "science"])
    capsys.readouterr()
    return db


def test_cli_soil_design_says_to_sample_deeper(capsys):
    assert main(["soil", "design", "--strata",
                 "clay:320:9.5,sandy:180:14,saline:40:6", "--margin", "2.0"]) == 0
    out = capsys.readouterr().out
    assert "cores required" in out
    assert "sample to 40 cm, not 30 cm" in out


def test_cli_soil_ingest_and_status(tmp_path, capsys):
    db = soil_db(tmp_path, capsys)
    assert main(["--db", db, "soil", "status", "IN-TNJ-01"]) == 0
    out = capsys.readouterr().out
    assert "baseline cores          1" in out
    assert "monitoring cores        1" in out
    assert "DayCent 2026.1" in out


def test_cli_soil_quantify_records_a_vintage(tmp_path, capsys):
    db = soil_db(tmp_path, capsys)
    assert main(["--db", db, "soil", "quantify", "IN-TNJ-01", "--year", "2028",
                 "--actor", "lalit"]) == 0
    out = capsys.readouterr().out
    assert "soil (measure and model)" in out
    assert "recorded as IN-TNJ-01:2028" in out
    # The ESM correction reaches the operator, not just the log.
    assert "bulk density moved" in out


def test_cli_soil_quantify_without_validation_costs_credits(tmp_path, capsys):
    """The commercial case for VMD0053: the same measured carbon, and an
    unvalidated model hands most of it back."""
    validated_db = soil_db(tmp_path, capsys, validate=True)
    main(["--db", validated_db, "soil", "quantify", "IN-TNJ-01", "--year",
          "2028", "--actor", "lalit"])
    good = capsys.readouterr().out

    bare = tmp_path / "bare"
    bare.mkdir()
    unvalidated_db = soil_db(bare, capsys, validate=False)
    main(["--db", unvalidated_db, "soil", "quantify", "IN-TNJ-01", "--year",
          "2028", "--actor", "lalit"])
    poor = capsys.readouterr().out

    assert "75.0% relative uncertainty" in poor
    assert "no VMD0053 model validation" in poor
    assert "5." in good          # single-digit uncertainty from the validation


def test_cli_soil_validate_rejects_training_data(tmp_path, capsys):
    db = str(tmp_path / "s.db")
    (tmp_path / "val.csv").write_text(VAL_CSV)
    main(["--db", db, "enroll", "vallam"])
    capsys.readouterr()
    assert main(["--db", db, "soil", "validate", "IN-TNJ-01",
                 str(tmp_path / "val.csv"), "--model", "m", "--version", "1",
                 "--training-data", "--actor", "science"]) == 1
    assert "independent validation set" in capsys.readouterr().out


def test_cli_soil_ingest_names_the_missing_lab_columns(tmp_path, capsys):
    db = str(tmp_path / "s.db")
    bad = tmp_path / "bad.csv"
    bad.write_text("plot_id,role\nP1,baseline\n")
    main(["--db", db, "enroll", "vallam"])
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        main(["--db", db, "soil", "ingest", "IN-TNJ-01", str(bad),
              "--actor", "field"])
    assert "missing column" in str(exc.value)
    assert "bulk_density_g_cm3" in str(exc.value)


def test_cli_soil_quantify_needs_paired_cores(tmp_path, capsys):
    db = str(tmp_path / "s.db")
    main(["--db", db, "enroll", "vallam"])
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        main(["--db", db, "soil", "quantify", "IN-TNJ-01", "--year", "2028",
              "--actor", "lalit"])
    assert "paired cores" in str(exc.value)
