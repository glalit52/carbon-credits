import json
from datetime import date

import pytest

from carbonstack import evidence, ledger, methodology, payments, pipeline
from carbonstack.api import dispatch
from carbonstack.feed import FeedProvider, series
from carbonstack.methodology.vm0047 import PerformanceBenchmark
from carbonstack.sites import NYERI, THANJAVUR, as_project
from carbonstack.store import Store


@pytest.fixture
def coffee():
    with Store(":memory:", actor="tester") as s:
        s.save_project(as_project(NYERI), methodology_id="VM0047")
        yield s


def coffee_provider(end=date(2030, 12, 31)):
    return FeedProvider(series(NYERI, NYERI.enrolled_on, end, stumping_year=2026))


# --- pipeline ---------------------------------------------------------------

def test_monitor_stores_observations_and_reports(coffee):
    report = pipeline.monitor(coffee, NYERI.id, coffee_provider(),
                              start=date(2026, 1, 1), end=date(2026, 3, 1))
    assert report.plots == 1
    assert report.retrievals > 0
    assert report.coverage == 1.0
    assert set(report.variables) == {"canopy_height_m", "stocking_index"}
    assert coffee.observation_count(NYERI.id) == report.stored
    # The provider composites over a window, so several step dates legitimately
    # resolve to the same underlying pass. Fewer stored than retrieved is the
    # deduplication working, not data being lost.
    assert 0 < report.stored <= report.retrievals


def test_monitor_is_rerunnable_without_duplicating(coffee):
    """Providers backfill and jobs get re-run. A second pass over the same
    window must store nothing new."""
    kw = dict(start=date(2026, 1, 1), end=date(2026, 3, 1))
    first = pipeline.monitor(coffee, NYERI.id, coffee_provider(), **kw)
    second = pipeline.monitor(coffee, NYERI.id, coffee_provider(), **kw)
    assert first.stored > 0
    assert second.stored == 0
    assert second.retrievals == first.retrievals


def test_monitor_reports_a_conflict_with_ground_truth(coffee):
    """A satellite and a field plot that disagree beyond their error bars is a
    finding. Averaging it away is where over-crediting starts."""
    from carbonstack.remote_sensing import FieldPlotProvider

    plot_id = next(iter(coffee.load_project(NYERI.id).plots))
    liar = FieldPlotProvider({(plot_id, "canopy_height_m", 2026): (40.0, 0.2, "m")})
    report = pipeline.monitor(coffee, NYERI.id, coffee_provider(),
                              start=date(2026, 6, 1), end=date(2026, 6, 20),
                              ground_truth=liar)
    assert report.conflicts
    assert "sigma apart" in report.conflicts[0]


def test_health_flags_a_project_that_is_not_being_monitored(coffee):
    h = pipeline.health(coffee, NYERI.id)
    assert h["never_monitored"] is True
    assert h["observations"] == 0

    pipeline.monitor(coffee, NYERI.id, coffee_provider(),
                     start=date(2026, 1, 1), end=date(2026, 3, 1))
    h = pipeline.health(coffee, NYERI.id)
    assert h["never_monitored"] is False
    assert h["monitoring_stale"] is True          # the window ended long ago


def test_quantify_records_a_draft_and_carries_extra_warnings(coffee):
    m = methodology.get("VM0047",
                        benchmark=PerformanceBenchmark(t_co2e_per_ha_yr=0.6))
    v = pipeline.quantify(coffee, NYERI.id, m, coffee_provider(), 2029,
                          actor="lalit", extra_warnings=["pollarding in window"])
    assert v.status is ledger.VintageStatus.DRAFT
    assert v.net_t > 0
    assert "pollarding in window" in v.warnings


def test_extra_warnings_force_a_reason_at_approval(coffee):
    """The only thing that makes a warning matter is that it blocks something."""
    from carbonstack.store import StoreError

    m = methodology.get("VM0047",
                        benchmark=PerformanceBenchmark(t_co2e_per_ha_yr=0.6))
    v = pipeline.quantify(coffee, NYERI.id, m, coffee_provider(), 2029,
                          extra_warnings=["pollarding in window"])
    ledger.submit_for_review(coffee, v.id, actor="a")
    with pytest.raises(StoreError, match="requires a note"):
        ledger.approve(coffee, v.id, actor="b")


# --- api --------------------------------------------------------------------

def issued_store():
    s = Store(":memory:", actor="tester")
    s.save_project(as_project(NYERI), methodology_id="VM0047")
    m = methodology.get("VM0047",
                        benchmark=PerformanceBenchmark(t_co2e_per_ha_yr=0.6))
    pipeline.monitor(s, NYERI.id, coffee_provider(),
                     start=date(2026, 1, 1), end=date(2029, 12, 31), step_days=30)
    v = pipeline.quantify(s, NYERI.id, m, coffee_provider(), 2029)
    return s, v


def test_api_reads():
    s, v = issued_store()
    assert dispatch(s, "GET", "/api/health", {}, {})[0] == 200
    assert dispatch(s, "GET", "/api/projects", {}, {})[1]["projects"][0]["id"] == NYERI.id

    status, body = dispatch(s, "GET", f"/api/projects/{NYERI.id}", {}, {})
    assert status == 200 and body["area_ha"] == pytest.approx(NYERI.area_ha, abs=1e-3)

    status, body = dispatch(s, "GET", f"/api/vintages/{v.id}/derivation", {}, {})
    assert status == 200 and body["calculations"]

    assert dispatch(s, "GET", "/api/queue", {}, {})[1]["queue"][0]["id"] == v.id


def test_api_unknown_route_is_404():
    s, _ = issued_store()
    assert dispatch(s, "GET", "/api/nothing", {}, {})[0] == 404


def test_api_write_demands_an_actor():
    s, v = issued_store()
    status, body = dispatch(s, "POST", f"/api/vintages/{v.id}/submit", {}, {})
    assert status == 400
    assert "actor" in body["error"]


def test_api_refused_transition_is_409_not_500():
    """A refused operation is the caller's state assumption being wrong, which
    is a useful thing for a client to be told precisely."""
    s, v = issued_store()
    status, body = dispatch(s, "POST", f"/api/vintages/{v.id}/issue",
                            {}, {"actor": "b", "registry": "Verra"})
    assert status == 409
    assert "approved" in body["error"]


def test_api_drives_the_whole_lifecycle():
    s, v = issued_store()
    assert dispatch(s, "POST", f"/api/vintages/{v.id}/submit",
                    {}, {"actor": "a"})[0] == 200
    assert dispatch(s, "POST", f"/api/vintages/{v.id}/approve",
                    {}, {"actor": "b", "note": "clear"})[0] == 200

    status, iss = dispatch(s, "POST", f"/api/vintages/{v.id}/issue",
                           {}, {"actor": "b", "registry": "Verra"})
    assert status == 200 and iss["quantity"] >= 1

    status, raised = dispatch(s, "POST", f"/api/vintages/{v.id}/payments", {},
                              {"actor": "l", "price_per_credit": 26,
                               "farmer_share": 0.6})
    assert status == 200 and raised["raised"] == 1

    pid = raised["payments"][0]["id"]
    assert dispatch(s, "POST", f"/api/payments/{pid}/approve",
                    {}, {"actor": "l"})[0] == 200
    status, paid = dispatch(s, "POST", f"/api/payments/{pid}/paid",
                            {}, {"actor": "l", "reference": "MPESA/1"})
    assert status == 200 and paid["status"] == "paid"

    assert dispatch(s, "GET", "/api/integrity", {}, {})[1]["chain_intact"] is True


def test_api_marking_paid_needs_a_reference():
    s, v = issued_store()
    dispatch(s, "POST", f"/api/vintages/{v.id}/submit", {}, {"actor": "a"})
    dispatch(s, "POST", f"/api/vintages/{v.id}/approve", {}, {"actor": "b", "note": "x"})
    dispatch(s, "POST", f"/api/vintages/{v.id}/issue", {}, {"actor": "b", "registry": "Verra"})
    _, raised = dispatch(s, "POST", f"/api/vintages/{v.id}/payments", {},
                         {"actor": "l", "price_per_credit": 26, "farmer_share": 0.6})
    pid = raised["payments"][0]["id"]
    dispatch(s, "POST", f"/api/payments/{pid}/approve", {}, {"actor": "l"})
    status, body = dispatch(s, "POST", f"/api/payments/{pid}/paid", {}, {"actor": "l"})
    assert status == 400 and "reference" in body["error"]


def test_api_raise_payments_validates_terms():
    s, v = issued_store()
    status, body = dispatch(s, "POST", f"/api/vintages/{v.id}/payments", {},
                            {"actor": "l", "price_per_credit": 26})
    assert status == 400 and "farmer_share" in body["error"]


# --- evidence ---------------------------------------------------------------

def test_evidence_pack_is_self_contained(tmp_path):
    s, v = issued_store()
    ledger.submit_for_review(s, v.id, actor="a")
    ledger.approve(s, v.id, actor="b", note="clear")
    ledger.issue(s, v.id, registry="Verra", actor="b")
    payments.raise_payments(
        s, v.id, payments.PaymentTerms(price_per_credit=26, farmer_share=0.6))

    out = evidence.build(s, NYERI.id, tmp_path / "pack")
    names = {p.name for p in out.iterdir()}
    assert {"manifest.json", "SUMMARY.md", "plot_register.csv", "observations.csv",
            "vintages.csv", "issuances.csv", "payments.csv", "derivations.json",
            "event_log.csv"} <= names

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["integrity"]["chain_intact"] is True
    assert manifest["credits"]["issued_credits"] >= 1
    assert manifest["caveats"]                       # placeholders are declared

    summary = (out / "SUMMARY.md").read_text()
    assert "Hash chain: **intact**" in summary
    assert NYERI.label in summary


def test_evidence_pack_reports_a_broken_chain_rather_than_hiding_it(tmp_path):
    """A pack that quietly omits a failed integrity check is worse than no
    pack. The verifier has to see it."""
    s, v = issued_store()
    s.conn.execute("UPDATE events SET payload_json = '{}' WHERE id = 1")
    s.conn.commit()

    out = evidence.build(s, NYERI.id, tmp_path / "pack")
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["integrity"]["chain_intact"] is False
    assert manifest["integrity"]["first_bad_event"] == "1"
    assert "BROKEN" in (out / "SUMMARY.md").read_text()


def test_evidence_plot_register_names_the_exclusion_reason(tmp_path):
    from carbonstack.domain import TenureBasis

    with Store(":memory:", actor="t") as s:
        project = as_project(THANJAVUR)
        plot = next(iter(project.plots.values()))
        plot.tenure = TenureBasis.UNDOCUMENTED
        plot.tenure_reference = ""
        s.save_project(project, methodology_id="VM0042")

        out = evidence.build(s, THANJAVUR.id, tmp_path / "pack")
        register = (out / "plot_register.csv").read_text()
        assert "creditable" in register
        assert "undocumented" in register
        assert ",no," in register or register.rstrip().endswith("undocumented")
