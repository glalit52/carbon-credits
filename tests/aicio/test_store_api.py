"""Persistence, the audit chain, connectors and the HTTP surface."""

from __future__ import annotations

import base64
import json
from datetime import date

import pytest

from aicio.api import _ANALYSIS_CACHE, dispatch
from aicio.crypto import CryptoError
from aicio.domain import DecisionOutcome, DecisionRecord
from aicio.market.connectors import (
    ConnectorError, ConsentError, MemoryVault, SandboxBrokerConnector, default_registry,
    grant_consent,
)
from aicio.store import StoreError
from aicio.store.repo import EncryptedTokenVault


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

def test_migrations_apply_once_and_are_idempotent(store, tmp_path):
    from aicio.store import Store
    assert store.version >= 2
    reopened = Store(tmp_path / "test.db", actor="test")
    assert reopened.version == store.version
    reopened.close()


def test_a_portfolio_round_trips_including_cash(seeded_store, bundle):
    """Cash has no instrument behind it, so it needs somewhere of its own --
    without it a reload silently reports a net worth missing the cash."""
    loaded = seeded_store.load_portfolio("user_demo")
    original = bundle["portfolio"]
    assert len(loaded.holdings) == len(original.holdings)
    assert loaded.cash == original.cash
    assert loaded.external_liabilities == original.external_liabilities
    assert loaded.net_worth == original.net_worth


def test_reimporting_replaces_rather_than_accumulates(seeded_store, bundle):
    """A sold fund that haunts a dashboard for months is worse than a slow
    import."""
    seeded_store.save_portfolio(bundle["portfolio"])
    assert len(seeded_store.load_portfolio("user_demo").holdings) == \
        len(bundle["portfolio"].holdings)


def test_transactions_are_not_duplicated_on_re_save(seeded_store, bundle):
    before = len(seeded_store.load_portfolio("user_demo").transactions)
    seeded_store.save_portfolio(bundle["portfolio"])
    assert len(seeded_store.load_portfolio("user_demo").transactions) == before


def test_profile_and_goals_round_trip(seeded_store, bundle):
    profile = seeded_store.load_profile("user_demo")
    assert profile.risk_capacity == bundle["profile"].risk_capacity
    assert profile.marginal_tax_rate == bundle["profile"].marginal_tax_rate
    assert len(seeded_store.load_goals("user_demo")) == len(bundle["goals"])


def test_a_missing_user_raises_rather_than_returning_empty(store):
    with pytest.raises(StoreError):
        store.load_user("nobody")


# ---------------------------------------------------------------------------
# Audit chain
# ---------------------------------------------------------------------------

def test_every_write_lands_in_the_audit_log(seeded_store):
    events = {e["event"] for e in seeded_store.audit_trail("user_demo", limit=50)}
    assert {"user.saved", "profile.saved", "policy.saved", "portfolio.saved"} <= events


def test_the_chain_verifies(seeded_store):
    intact, bad = seeded_store.verify_chain()
    assert intact and bad is None


def test_editing_history_is_detectable(seeded_store):
    """Which is what 'maintain audit logs' has to mean to be worth anything."""
    seeded_store.connection.execute(
        "UPDATE audit_events SET event = 'tampered' WHERE id = 2"
    )
    seeded_store.connection.commit()
    intact, bad = seeded_store.verify_chain()
    assert not intact and bad == 2


def test_deleting_a_row_is_detectable(seeded_store):
    seeded_store.connection.execute("DELETE FROM audit_events WHERE id = 2")
    seeded_store.connection.commit()
    intact, _ = seeded_store.verify_chain()
    assert not intact


def test_an_approval_is_always_recorded(seeded_store):
    seeded_store.record_decision(DecisionRecord(
        id="d1", user_id="user_demo", recommendation_id="rec_1",
        outcome=DecisionOutcome.ACCEPTED, note="agreed",
    ))
    assert any(e["event"] == "decision.recorded"
               for e in seeded_store.audit_trail("user_demo"))
    assert seeded_store.decision_history("user_demo")[0].outcome is DecisionOutcome.ACCEPTED


# ---------------------------------------------------------------------------
# Encryption at rest
# ---------------------------------------------------------------------------

def test_documents_are_sealed_on_disk(seeded_store):
    store = seeded_store
    document_id = store.store_document("user_demo", "cas.pdf", b"SECRET FOLIO 12345")
    raw = store.connection.execute(
        "SELECT sealed FROM documents WHERE id = ?", (document_id,)
    ).fetchone()[0]
    assert b"SECRET" not in raw
    assert store.read_document(document_id)[1] == b"SECRET FOLIO 12345"


def test_a_document_read_is_audited(seeded_store):
    store = seeded_store
    document_id = store.store_document("user_demo", "cas.pdf", b"x")
    store.read_document(document_id)
    assert any(e["event"] == "document.read" for e in store.audit_trail("user_demo"))


def test_tokens_never_touch_disk_in_plaintext(seeded_store):
    store = seeded_store
    vault = EncryptedTokenVault(store)
    vault.put("user_demo", "sandbox", {"access_token": "super-secret-token"})
    raw = store.connection.execute("SELECT sealed FROM connector_tokens").fetchone()[0]
    assert b"super-secret-token" not in raw
    assert vault.get("user_demo", "sandbox")["access_token"] == "super-secret-token"


def test_the_audit_entry_for_a_token_does_not_contain_the_token(seeded_store):
    store = seeded_store
    EncryptedTokenVault(store).put("user_demo", "sandbox", {"access_token": "abc123"})
    rows = store.connection.execute(
        "SELECT payload_json FROM audit_events WHERE event = 'connector.token_stored'"
    ).fetchall()
    assert rows and "abc123" not in rows[0][0]


def test_a_document_for_an_unknown_user_names_the_cause(store):
    with pytest.raises(StoreError, match="unknown user"):
        store.store_document("nobody", "cas.pdf", b"x")


def test_storage_without_a_key_fails_loudly(tmp_path):
    from aicio.store import Store
    store = Store(tmp_path / "nokey.db", actor="test")
    with pytest.raises(StoreError, match="no encryption key"):
        store.store_document("u", "f.pdf", b"x")
    store.close()


# ---------------------------------------------------------------------------
# Erasure
# ---------------------------------------------------------------------------

def test_erasure_removes_the_data_but_keeps_the_proof(seeded_store):
    """The audit log holds no financial detail and is what proves the erasure
    happened, which is how the right to erasure and the duty to keep records
    stay compatible."""
    seeded_store.delete_user_data("user_demo")
    with pytest.raises(StoreError):
        seeded_store.load_user("user_demo")
    assert seeded_store.load_portfolio("user_demo").holdings == []
    assert any(e["event"] == "user.erased" for e in seeded_store.audit_trail("user_demo"))
    assert seeded_store.verify_chain()[0]


def test_consent_is_revocable_without_erasing_that_it_existed(seeded_store):
    assert seeded_store.revoke_consent("user_demo", "portfolio_analysis") == 1
    user = seeded_store.load_user("user_demo")
    assert not user.has_consent("portfolio_analysis")
    rows = seeded_store.connection.execute(
        "SELECT revoked_at FROM consents WHERE purpose = 'portfolio_analysis'"
    ).fetchall()
    assert rows and rows[0][0] is not None


# ---------------------------------------------------------------------------
# Connectors
# ---------------------------------------------------------------------------

def test_every_shipped_connector_is_listed_even_without_keys():
    """The connection screen should say Zerodha needs setup, not hide it."""
    registry = default_registry()
    keys = {c["key"] for c in registry.available()}
    assert {"zerodha_kite", "upstox", "angel_one", "account_aggregator",
            "plaid", "snaptrade"} <= keys
    unconfigured = [c for c in registry.available() if c["status"] == "unconfigured"]
    assert all(c["missing_keys"] for c in unconfigured)


def test_data_cannot_be_fetched_without_consent():
    """A connector that quietly returns nothing looks like an empty account."""
    connector = SandboxBrokerConnector(MemoryVault())
    with pytest.raises(ConsentError):
        connector.fetch_holdings("u1")


def test_an_expired_consent_is_refused():
    connector = SandboxBrokerConnector(MemoryVault())
    consent = connector.exchange("u1", {})
    consent.revoke()
    with pytest.raises(ConsentError):
        connector.fetch_holdings("u1", consent)


def test_a_consent_does_not_cover_a_scope_it_did_not_grant():
    consent = grant_consent("u1", "sandbox", purpose="analysis", scope=("holdings",))
    assert consent.covers("holdings")
    assert not consent.covers("transactions")


def test_connected_holdings_go_through_the_same_parse_contract():
    connector = SandboxBrokerConnector(MemoryVault())
    result = connector.fetch_holdings("u1", connector.exchange("u1", {}))
    assert result.source_format == "connector"
    assert result.confidence == 1.0
    assert len(result.holdings) == len(result.assets)
    assert all(h.provenance.kind.value == "connected_account" for h in result.holdings)


def test_an_unknown_connector_is_an_error_not_a_crash():
    with pytest.raises(ConnectorError):
        default_registry().get("imaginary_bank")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_cache():
    _ANALYSIS_CACHE.clear()
    yield
    _ANALYSIS_CACHE.clear()


@pytest.mark.parametrize("path", [
    "/api/health", "/api/connectors",
    "/api/users/user_demo/dashboard", "/api/users/user_demo/portfolio",
    "/api/users/user_demo/xray", "/api/users/user_demo/actions",
    "/api/users/user_demo/goals", "/api/users/user_demo/risk",
    "/api/users/user_demo/tax", "/api/users/user_demo/sips",
    "/api/users/user_demo/policy", "/api/users/user_demo/audit",
    "/api/users/user_demo/reports/daily", "/api/users/user_demo/reports/weekly",
    "/api/users/user_demo/reports/monthly",
])
def test_read_endpoints_answer(seeded_store, path):
    status, payload = dispatch(seeded_store, "GET", path, {}, {})
    assert status == 200, payload
    assert json.dumps(payload, default=str)


def test_unknown_routes_and_reports_404(seeded_store):
    assert dispatch(seeded_store, "GET", "/api/nope", {}, {})[0] == 404
    assert dispatch(seeded_store, "GET", "/api/users/user_demo/reports/yearly", {}, {})[0] == 404


def test_a_user_with_no_portfolio_is_told_to_import(store):
    status, payload = dispatch(store, "GET", "/api/users/ghost/dashboard", {}, {})
    assert status == 404
    assert "import" in payload["error"]


def test_the_dashboard_answers_in_one_call(seeded_store):
    _, payload = dispatch(seeded_store, "GET", "/api/users/user_demo/dashboard", {}, {})
    for key in ("net_worth", "health", "allocation", "goals", "actions", "alerts"):
        assert key in payload


def test_importing_a_statement_merges_and_audits(seeded_store):
    csv = ("Scheme Name,ISIN,Units,NAV,Average Cost\n"
           "New Equity Fund,INF999999999,100,250.00,200.00\n")
    status, payload = dispatch(
        seeded_store, "POST", "/api/users/user_demo/import", {},
        {"filename": "extra.csv", "content_base64": base64.b64encode(csv.encode()).decode()},
    )
    assert status == 200
    assert payload["parse"]["confidence"] == 1.0
    assert any(e["event"] == "statement.imported"
               for e in seeded_store.audit_trail("user_demo"))


def test_a_bad_upload_is_rejected_with_a_reason(seeded_store):
    status, payload = dispatch(
        seeded_store, "POST", "/api/users/user_demo/import", {},
        {"filename": "x.csv", "content_base64": "!!!not base64!!!"},
    )
    assert status == 400 and "base64" in payload["error"]


def test_connecting_an_account_records_the_consent(seeded_store):
    status, payload = dispatch(
        seeded_store, "POST", "/api/users/user_demo/connect/sandbox", {}, {},
    )
    assert status == 200
    assert payload["consent"]["active"]
    assert payload["imported"]["holdings"] == 3
    assert any(e["event"] == "account.connected"
               for e in seeded_store.audit_trail("user_demo"))


def test_asking_the_banker_stores_the_conversation(seeded_store):
    status, payload = dispatch(
        seeded_store, "POST", "/api/users/user_demo/ask", {},
        {"question": "How am I doing?"},
    )
    assert status == 200
    assert payload["text"] and payload["grounding"]["grounded"]
    conversation = seeded_store.load_conversation(payload["conversation_id"])
    assert len(conversation.messages) == 2


def test_recording_a_decision_does_not_execute_anything(seeded_store):
    """Recommending and executing are separate systems; this endpoint lives
    entirely on the recommending side."""
    _, actions = dispatch(seeded_store, "GET", "/api/users/user_demo/actions", {}, {})
    recommendation_id = actions["recommendations"][0]["id"]
    status, payload = dispatch(
        seeded_store, "POST", "/api/users/user_demo/decisions", {},
        {"recommendation_id": recommendation_id, "outcome": "accepted"},
    )
    assert status == 200 and payload["recorded"]
    assert seeded_store.decision_history("user_demo")


def test_an_invalid_outcome_lists_the_valid_ones(seeded_store):
    status, payload = dispatch(
        seeded_store, "POST", "/api/users/user_demo/decisions", {},
        {"recommendation_id": "rec_1", "outcome": "maybe"},
    )
    assert status == 400 and "accepted" in payload["valid_outcomes"]


def test_erasure_through_the_api(seeded_store):
    status, payload = dispatch(seeded_store, "DELETE", "/api/users/user_demo", {}, {})
    assert status == 200 and payload["erased"]
    assert dispatch(seeded_store, "GET", "/api/users/user_demo/dashboard", {}, {})[0] == 404


def test_the_analysis_cache_invalidates_when_the_portfolio_changes(seeded_store, bundle):
    _, first = dispatch(seeded_store, "GET", "/api/users/user_demo/dashboard", {}, {})
    csv = ("Scheme Name,ISIN,Units,NAV,Average Cost\n"
           "Another Fund,INF888888888,500,100.00,80.00\n")
    dispatch(seeded_store, "POST", "/api/users/user_demo/import", {},
             {"filename": "more.csv",
              "content_base64": base64.b64encode(csv.encode()).decode()})
    _, second = dispatch(seeded_store, "GET", "/api/users/user_demo/dashboard", {}, {})
    assert second["net_worth"] > first["net_worth"]
    assert second["fingerprint"] != first["fingerprint"]
