"""The committed dashboard, and the command line."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from aicio.cli import main
from aicio.web.build import DASHBOARD_TRIALS, DEFAULT_QUESTIONS, build_payload, render

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "aicio_dashboard" / "index.html"

PAYLOAD = re.compile(
    r'<script type="application/json" id="payload">(.*?)</script>', re.S
)


def _committed() -> dict:
    raw = PAYLOAD.search(DASHBOARD.read_text()).group(1)
    return json.loads(raw.replace("<\\/", "</"))


def test_the_committed_dashboard_exists():
    assert DASHBOARD.exists(), "run scripts/build_aicio_dashboard.py"


def test_the_committed_dashboard_matches_the_code_that_generates_it(bundle):
    """The page is committed rather than built on deploy, so it can drift from
    the engine. Timestamps differ every run by design; everything that carries
    meaning is compared strictly.

    Rebuilt at the same trial count the build script pins, so a simulation
    difference cannot masquerade as drift.
    """
    from aicio.analysis import analyse
    from aicio.decisions import generate

    rebuilt = analyse(
        bundle["portfolio"], bundle["profile"], bundle["policy"], bundle["goals"],
        today=bundle["as_of"], quality=bundle["quality"], behaviour=bundle["behaviour"],
        monte_carlo_trials=DASHBOARD_TRIALS,
    )
    committed = _committed()
    fresh = build_payload(
        rebuilt, generate(rebuilt, today=bundle["as_of"], limit=0), include_chat=False,
    )
    for key in ("net_worth", "market_value", "invested", "cash", "engine_version"):
        assert committed[key] == fresh[key], f"{key} has drifted; rebuild the dashboard"
    assert committed["health"]["score"] == fresh["health"]["score"]
    assert [a["id"] for a in committed["actions"]] == [a["id"] for a in fresh["actions"]]


def test_the_page_carries_its_data_and_needs_no_network():
    text = DASHBOARD.read_text()
    assert "<script type=\"application/json\" id=\"payload\">" in text
    for remote in ("http://", "https://", "fonts.googleapis", "cdn."):
        assert remote not in text, f"the dashboard must not reach for {remote}"


def test_the_payload_cannot_break_out_of_its_script_tag():
    """The only sequence that can escape a JSON script block is a literal
    closing tag, so it is escaped on the way in."""
    payload = {"note": "</script><script>alert(1)</script>"}
    rendered = render({**payload, "health": {}, "actions": []})
    assert "</script><script>alert" not in rendered


def test_the_page_answers_the_questions_a_client_opens_it_to_ask(analysis, recommendations):
    payload = build_payload(analysis, recommendations)
    assert [c["question"] for c in payload["chat"]] == list(DEFAULT_QUESTIONS)
    assert all(c["grounded"] for c in payload["chat"])


def test_every_published_answer_passed_the_grounding_gate():
    assert all(entry["grounded"] for entry in _committed()["chat"])


def test_the_page_discloses_what_it_could_not_assess():
    committed = _committed()
    assert "unassessed" in committed["health"]
    assert 0 < committed["xray"]["coverage"] <= 1


def test_the_page_states_it_is_not_advice():
    assert "not regulated investment advice" in DASHBOARD.read_text()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_demo_runs_the_whole_product(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "demo.db"), "demo", "--limit", "3"]) == 0
    out = capsys.readouterr().out
    assert "ACTION CENTRE" in out and "AI BANKER" in out
    assert "Daily brief" in out


def test_evals_exit_zero_when_the_suite_passes(capsys):
    assert main(["evals"]) == 0
    assert "EVALUATION SUITE" in capsys.readouterr().out


def test_import_dry_run_reports_without_saving(tmp_path, capsys):
    path = tmp_path / "holdings.csv"
    path.write_text("Scheme Name,ISIN,Units,NAV,Average Cost\n"
                    "A Fund,INF000000001,100,50.00,40.00\n")
    assert main(["--db", str(tmp_path / "x.db"), "import", str(path), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "holdings     1" in out and "confidence   100%" in out


def test_import_reports_unreadable_rows(tmp_path, capsys):
    path = tmp_path / "bad.csv"
    path.write_text("Scheme Name,ISIN,Units,NAV\n"
                    "A Fund,INF000000001,100,50.00\n"
                    "B Fund,INF000000002,oops,50.00\n")
    main(["--db", str(tmp_path / "x.db"), "import", str(path), "--dry-run"])
    assert "! line" in capsys.readouterr().out


def test_a_missing_file_is_an_error_not_a_traceback(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "x.db"), "import", "/nope.csv"]) == 2


def test_connectors_lists_integrations_and_what_they_need(capsys):
    assert main(["connectors"]) == 0
    out = capsys.readouterr().out
    assert "zerodha_kite" in out and "account_aggregator" in out
    assert "needs AICIO_" in out


def test_audit_verifies_the_chain(tmp_path, capsys):
    db = tmp_path / "audit.db"
    main(["--db", str(db), "demo", "--limit", "1"])
    capsys.readouterr()
    assert main(["--db", str(db), "audit"]) == 0
    assert "audit chain: intact" in capsys.readouterr().out


def test_report_renders_from_a_seeded_database(tmp_path, capsys):
    db = tmp_path / "report.db"
    main(["--db", str(db), "demo", "--limit", "1"])
    capsys.readouterr()
    assert main(["--db", str(db), "report", "monthly"]) == 0
    assert "investment committee" in capsys.readouterr().out


def test_dashboard_builds_to_a_directory(tmp_path, capsys):
    out = tmp_path / "site"
    assert main(["--db", str(tmp_path / "d.db"), "dashboard", "--out", str(out)]) == 0
    assert (out / "index.html").exists() and (out / "data.json").exists()
