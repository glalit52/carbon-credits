"""Database schema and migrations.

SQLite, on purpose. A carbon project's record is small -- tens of thousands of
plots and a few million observations at national scale -- and it has to be
copyable, auditable and openable by a verification body that will not install
anything. A single file that anyone can read with sqlite3 is worth more here
than a server.

Migrations are an ordered list. Each runs once, inside a transaction, and the
applied version is recorded. Never edit a migration that has shipped; add
another one.
"""

from __future__ import annotations

import sqlite3

MIGRATIONS: list[tuple[int, str]] = [
    (1, """
    CREATE TABLE projects (
        id                   TEXT PRIMARY KEY,
        name                 TEXT NOT NULL,
        track                TEXT NOT NULL,
        country              TEXT NOT NULL,
        start_date           TEXT NOT NULL,
        crediting_period_yrs INTEGER NOT NULL DEFAULT 30,
        methodology_id       TEXT NOT NULL,
        registry             TEXT,
        registry_ref         TEXT,
        created_at           TEXT NOT NULL
    );

    CREATE TABLE farmers (
        id                TEXT PRIMARY KEY,
        project_id        TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name              TEXT NOT NULL,
        village           TEXT NOT NULL,
        district          TEXT NOT NULL,
        state             TEXT NOT NULL,
        consent_on        TEXT,
        consent_reference TEXT NOT NULL DEFAULT '',
        payee_reference   TEXT NOT NULL DEFAULT '',
        created_at        TEXT NOT NULL
    );
    CREATE INDEX idx_farmers_project ON farmers(project_id);

    CREATE TABLE plots (
        id               TEXT PRIMARY KEY,
        project_id       TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        farmer_id        TEXT NOT NULL REFERENCES farmers(id),
        boundary_json    TEXT NOT NULL,
        tenure           TEXT NOT NULL,
        tenure_reference TEXT NOT NULL DEFAULT '',
        surveyed_on      TEXT,
        area_ha          REAL NOT NULL,
        fingerprint      TEXT NOT NULL,
        created_at       TEXT NOT NULL
    );
    CREATE INDEX idx_plots_project ON plots(project_id);
    CREATE INDEX idx_plots_farmer  ON plots(farmer_id);

    CREATE TABLE enrollments (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        plot_id       TEXT NOT NULL REFERENCES plots(id),
        enrolled_on   TEXT NOT NULL,
        practice      TEXT NOT NULL,
        species_json  TEXT NOT NULL DEFAULT '[]',
        stems_planted INTEGER,
        created_at    TEXT NOT NULL,
        UNIQUE(project_id, plot_id)
    );

    CREATE TABLE observations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        plot_id     TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
        observed_on TEXT NOT NULL,
        variable    TEXT NOT NULL,
        value       REAL NOT NULL,
        unit        TEXT NOT NULL,
        source      TEXT NOT NULL,
        uncertainty REAL,
        created_at  TEXT NOT NULL,
        UNIQUE(plot_id, observed_on, variable, source)
    );
    CREATE INDEX idx_obs_lookup ON observations(plot_id, variable, observed_on);

    CREATE TABLE vintages (
        id                   TEXT PRIMARY KEY,
        project_id           TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        year                 INTEGER NOT NULL,
        methodology_id       TEXT NOT NULL,
        area_ha              REAL NOT NULL,
        gross_t              REAL NOT NULL,
        net_t                REAL NOT NULL,
        relative_uncertainty REAL NOT NULL,
        deductions_json      TEXT NOT NULL,
        warnings_json        TEXT NOT NULL,
        calculations_json    TEXT NOT NULL,
        status               TEXT NOT NULL,
        quantified_at        TEXT NOT NULL,
        UNIQUE(project_id, year)
    );

    CREATE TABLE issuances (
        id           TEXT PRIMARY KEY,
        vintage_id   TEXT NOT NULL REFERENCES vintages(id) ON DELETE CASCADE,
        quantity     REAL NOT NULL,
        serial_start TEXT NOT NULL,
        serial_end   TEXT NOT NULL,
        issued_on    TEXT NOT NULL,
        registry     TEXT NOT NULL,
        registry_ref TEXT NOT NULL DEFAULT '',
        created_at   TEXT NOT NULL
    );
    CREATE INDEX idx_issuances_vintage ON issuances(vintage_id);

    CREATE TABLE buffer_entries (
        id          TEXT PRIMARY KEY,
        vintage_id  TEXT NOT NULL REFERENCES vintages(id) ON DELETE CASCADE,
        quantity    REAL NOT NULL,
        reason      TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        released_at TEXT,
        release_note TEXT
    );
    CREATE INDEX idx_buffer_vintage ON buffer_entries(vintage_id);

    CREATE TABLE payments (
        id         TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        farmer_id  TEXT NOT NULL REFERENCES farmers(id),
        vintage_id TEXT NOT NULL REFERENCES vintages(id),
        credits    REAL NOT NULL,
        amount     REAL NOT NULL,
        currency   TEXT NOT NULL,
        status     TEXT NOT NULL,
        due_on     TEXT,
        paid_on    TEXT,
        reference  TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        UNIQUE(vintage_id, farmer_id)
    );
    CREATE INDEX idx_payments_project ON payments(project_id);
    CREATE INDEX idx_payments_farmer  ON payments(farmer_id);

    CREATE TABLE events (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        at           TEXT NOT NULL,
        actor        TEXT NOT NULL,
        kind         TEXT NOT NULL,
        subject_type TEXT NOT NULL,
        subject_id   TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        prev_hash    TEXT NOT NULL,
        hash         TEXT NOT NULL
    );
    CREATE INDEX idx_events_subject ON events(subject_type, subject_id);
    """),
]

LATEST = max(v for v, _ in MIGRATIONS)


def migrate(conn: sqlite3.Connection) -> int:
    """Bring a connection up to the latest schema. Returns the version."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] or 0

    for version, ddl in sorted(MIGRATIONS):
        if version <= current:
            continue
        conn.executescript(ddl)
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
        conn.commit()
        current = version
    return current
