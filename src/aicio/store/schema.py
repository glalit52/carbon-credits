"""Schema and migrations.

Migrations are an ordered list, each applied once inside a transaction with
its version recorded. A shipped migration is never edited -- another one is
added -- because the alternative is a database whose shape depends on when it
was created.
"""

from __future__ import annotations

import sqlite3

MIGRATIONS: list[tuple[int, str]] = [
    (1, """
    CREATE TABLE users (
        id          TEXT PRIMARY KEY,
        email       TEXT NOT NULL UNIQUE,
        name        TEXT NOT NULL DEFAULT '',
        country     TEXT NOT NULL DEFAULT 'IN',
        currency    TEXT NOT NULL DEFAULT 'INR',
        timezone    TEXT NOT NULL DEFAULT 'Asia/Kolkata',
        locale      TEXT NOT NULL DEFAULT 'en-IN',
        quiet_start INTEGER NOT NULL DEFAULT 22,
        quiet_end   INTEGER NOT NULL DEFAULT 7,
        channels    TEXT NOT NULL DEFAULT 'in_app',
        created_at  TEXT NOT NULL
    );

    -- Consent is per purpose and revocable, which the DPDP Act and the account
    -- aggregator framework both require. One row per grant, never updated in
    -- place, so a revocation does not erase the fact that consent existed.
    CREATE TABLE consents (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        purpose    TEXT NOT NULL,
        scope      TEXT NOT NULL DEFAULT '',
        connector  TEXT NOT NULL DEFAULT '',
        reference  TEXT NOT NULL DEFAULT '',
        granted_at TEXT NOT NULL,
        expires_at TEXT,
        revoked_at TEXT
    );
    CREATE INDEX idx_consents_user ON consents(user_id, purpose);

    CREATE TABLE financial_profiles (
        user_id            TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        payload_json       TEXT NOT NULL,
        risk_tolerance     INTEGER NOT NULL,
        risk_capacity      INTEGER NOT NULL,
        updated_at         TEXT NOT NULL
    );

    CREATE TABLE policies (
        id            TEXT PRIMARY KEY,
        user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        version       INTEGER NOT NULL,
        payload_json  TEXT NOT NULL,
        edited_by_user INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL
    );
    CREATE INDEX idx_policies_user ON policies(user_id, version DESC);

    CREATE TABLE goals (
        id            TEXT PRIMARY KEY,
        user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name          TEXT NOT NULL,
        goal_type     TEXT NOT NULL,
        target_amount TEXT NOT NULL,
        target_date   TEXT NOT NULL,
        priority      INTEGER NOT NULL DEFAULT 3,
        payload_json  TEXT NOT NULL,
        created_at    TEXT NOT NULL
    );
    CREATE INDEX idx_goals_user ON goals(user_id, priority);

    CREATE TABLE accounts (
        id           TEXT PRIMARY KEY,
        user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        institution  TEXT NOT NULL,
        account_type TEXT NOT NULL,
        currency     TEXT NOT NULL DEFAULT 'INR',
        masked       TEXT NOT NULL DEFAULT '',
        source       TEXT NOT NULL,
        connected_at TEXT,
        last_synced_at TEXT,
        active       INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX idx_accounts_user ON accounts(user_id);

    CREATE TABLE assets (
        id           TEXT PRIMARY KEY,
        name         TEXT NOT NULL,
        asset_type   TEXT NOT NULL,
        isin         TEXT NOT NULL DEFAULT '',
        scheme_code  TEXT NOT NULL DEFAULT '',
        ticker       TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL
    );
    CREATE INDEX idx_assets_isin ON assets(isin);

    CREATE TABLE holdings (
        id           TEXT PRIMARY KEY,
        user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        account_id   TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        asset_id     TEXT NOT NULL REFERENCES assets(id),
        units        TEXT NOT NULL,
        average_cost TEXT NOT NULL,
        price        TEXT NOT NULL,
        as_of        TEXT NOT NULL,
        provenance_json TEXT NOT NULL
    );
    CREATE UNIQUE INDEX idx_holdings_position ON holdings(account_id, asset_id);
    CREATE INDEX idx_holdings_user ON holdings(user_id);

    CREATE TABLE transactions (
        id           TEXT PRIMARY KEY,
        user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        account_id   TEXT NOT NULL,
        asset_id     TEXT NOT NULL,
        txn_type     TEXT NOT NULL,
        trade_date   TEXT NOT NULL,
        units        TEXT NOT NULL,
        price        TEXT NOT NULL,
        amount       TEXT NOT NULL,
        fees         TEXT NOT NULL DEFAULT '0',
        note         TEXT NOT NULL DEFAULT '',
        provenance_json TEXT NOT NULL
    );
    CREATE INDEX idx_txn_user ON transactions(user_id, trade_date);
    CREATE INDEX idx_txn_asset ON transactions(asset_id, trade_date);

    CREATE TABLE sips (
        id         TEXT PRIMARY KEY,
        user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        account_id TEXT NOT NULL,
        asset_id   TEXT NOT NULL,
        amount     TEXT NOT NULL,
        frequency  TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date   TEXT,
        goal_id    TEXT NOT NULL DEFAULT '',
        active     INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX idx_sips_user ON sips(user_id);

    CREATE TABLE snapshots (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        as_of      TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX idx_snapshot_day ON snapshots(user_id, as_of);

    -- The full analysis input snapshot is stored with each recommendation run,
    -- which is what makes "re-derive this decision exactly" a lookup rather
    -- than an archaeology project.
    CREATE TABLE recommendations (
        id            TEXT PRIMARY KEY,
        user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        as_of         TEXT NOT NULL,
        action        TEXT NOT NULL,
        priority      TEXT NOT NULL,
        subject_id    TEXT NOT NULL,
        rule_id       TEXT NOT NULL,
        confidence    REAL NOT NULL,
        engine_version TEXT NOT NULL,
        fingerprint   TEXT NOT NULL,
        suppressed    TEXT NOT NULL DEFAULT '',
        payload_json  TEXT NOT NULL,
        created_at    TEXT NOT NULL
    );
    CREATE INDEX idx_rec_user ON recommendations(user_id, as_of DESC);

    CREATE TABLE decisions (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id           TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        recommendation_id TEXT NOT NULL,
        outcome           TEXT NOT NULL,
        note              TEXT NOT NULL DEFAULT '',
        decided_at        TEXT NOT NULL
    );
    CREATE INDEX idx_decisions_user ON decisions(user_id, decided_at DESC);

    CREATE TABLE alerts (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        alert_type  TEXT NOT NULL,
        severity    TEXT NOT NULL,
        title       TEXT NOT NULL,
        body        TEXT NOT NULL,
        dedupe_key  TEXT NOT NULL,
        status      TEXT NOT NULL,
        useful      INTEGER,
        snooze_until TEXT,
        recommendation_id TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );
    CREATE INDEX idx_alerts_user ON alerts(user_id, status);
    CREATE UNIQUE INDEX idx_alerts_dedupe ON alerts(user_id, dedupe_key);

    CREATE TABLE conversations (
        id         TEXT PRIMARY KEY,
        user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL
    );

    CREATE TABLE messages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role            TEXT NOT NULL,
        content         TEXT NOT NULL,
        fact_ids        TEXT NOT NULL DEFAULT '',
        prompt_id       TEXT NOT NULL DEFAULT '',
        model           TEXT NOT NULL DEFAULT '',
        grounded        INTEGER,
        created_at      TEXT NOT NULL
    );
    CREATE INDEX idx_messages_conv ON messages(conversation_id, id);

    -- Uploaded statements, sealed. The blob column never holds plaintext; the
    -- key id records which key sealed it so a rotation is auditable.
    CREATE TABLE documents (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        filename    TEXT NOT NULL,
        media_type  TEXT NOT NULL DEFAULT '',
        sealed      BLOB NOT NULL,
        key_id      TEXT NOT NULL,
        sha256      TEXT NOT NULL,
        bytes       INTEGER NOT NULL,
        retain_until TEXT,
        created_at  TEXT NOT NULL
    );
    CREATE INDEX idx_documents_user ON documents(user_id);

    -- Access tokens, sealed under a different purpose from documents, so one
    -- cannot be substituted for the other even with the same key material.
    CREATE TABLE connector_tokens (
        user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        connector  TEXT NOT NULL,
        sealed     BLOB NOT NULL,
        key_id     TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, connector)
    );

    -- Hash-chained audit log. Each row commits to the previous one, so a
    -- deletion or edit inside the table is detectable rather than invisible.
    CREATE TABLE audit_events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     TEXT NOT NULL DEFAULT '',
        actor       TEXT NOT NULL,
        event       TEXT NOT NULL,
        subject     TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL DEFAULT '{}',
        prev_hash   TEXT NOT NULL,
        hash        TEXT NOT NULL,
        created_at  TEXT NOT NULL
    );
    CREATE INDEX idx_audit_user ON audit_events(user_id, id);

    """),
    (2, """
    -- Cash and liabilities are portfolio-level balances with no instrument
    -- behind them, so they have nowhere to live in `holdings`. Without this
    -- table a reload silently reported a net worth missing the cash, which is
    -- the kind of error a user spots immediately and never forgets.
    CREATE TABLE portfolio_state (
        user_id     TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        cash        TEXT NOT NULL DEFAULT '0',
        liabilities TEXT NOT NULL DEFAULT '0',
        updated_at  TEXT NOT NULL
    );
    """),
]


def migrate(connection: sqlite3.Connection) -> int:
    """Apply every migration not yet applied. Returns the resulting version."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {
        row[0] for row in connection.execute("SELECT version FROM schema_version")
    }
    from datetime import datetime, timezone

    for version, ddl in MIGRATIONS:
        if version in applied:
            continue
        with connection:
            connection.executescript(ddl)
            connection.execute(
                "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )
    row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] or 0
