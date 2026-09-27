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
    (2, """
    -- Registry-blocking records the first schema had no room for. Each one
    -- is something a validation and verification body asks for and the
    -- product could not answer: which version of the rules a number was
    -- computed under, who holds the right to the credits, whether the
    -- baseline predates the practice change, and whether the field is the
    -- kind of rice a rice methodology will credit at all.
    ALTER TABLE projects    ADD COLUMN methodology_version TEXT NOT NULL DEFAULT '';
    ALTER TABLE projects    ADD COLUMN consultation_json   TEXT;
    ALTER TABLE farmers     ADD COLUMN carbon_rights_json  TEXT;
    ALTER TABLE enrollments ADD COLUMN baseline_captured_on TEXT;
    ALTER TABLE enrollments ADD COLUMN practice_started_on  TEXT;
    ALTER TABLE enrollments ADD COLUMN ecosystem            TEXT;
    ALTER TABLE enrollments ADD COLUMN water_control        TEXT;

    -- Stacking. A hectare may carry more than one pillar only on separate
    -- geometry and under methodologies that do not credit the same pool.
    CREATE TABLE pillar_claims (
        id             TEXT PRIMARY KEY,
        project_id     TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        plot_id        TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
        pillar         TEXT NOT NULL,
        methodology_id TEXT NOT NULL,
        carbon_pool    TEXT NOT NULL,
        area_ha        REAL NOT NULL,
        geometry_json  TEXT,
        created_at     TEXT NOT NULL,
        UNIQUE(plot_id, pillar)
    );
    CREATE INDEX idx_pillar_plot ON pillar_claims(plot_id);
    """),
    (3, """
    -- Soil. The one pathway whose numbers come from a physical core and an
    -- accredited lab rather than a satellite, so the lab reference and the
    -- sampling date are part of the evidence, not metadata about it.
    CREATE TABLE soil_cores (
        id            TEXT PRIMARY KEY,
        project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        plot_id       TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
        sampled_on    TEXT NOT NULL,
        lab_reference TEXT NOT NULL,
        stratum       TEXT NOT NULL DEFAULT '',
        role          TEXT NOT NULL,          -- baseline | monitoring
        layers_json   TEXT NOT NULL,
        created_at    TEXT NOT NULL,
        UNIQUE(plot_id, sampled_on, role)
    );
    CREATE INDEX idx_cores_project ON soil_cores(project_id, role);

    -- VMD0053. A model result is only evidence if somebody validated the
    -- model, so the validation is stored beside the numbers it justifies.
    CREATE TABLE model_validations (
        id            TEXT PRIMARY KEY,
        project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        model_name    TEXT NOT NULL,
        model_version TEXT NOT NULL,
        held_out      INTEGER NOT NULL,
        pairs_json    TEXT NOT NULL,
        rmse_t_ha     REAL NOT NULL,
        bias_t_ha     REAL NOT NULL,
        r_squared     REAL NOT NULL,
        relative_uncertainty REAL NOT NULL,
        accepted      INTEGER NOT NULL,
        created_at    TEXT NOT NULL
    );
    CREATE INDEX idx_validations_project ON model_validations(project_id);
    """),
    (4, """
    -- Article 6. Who is allowed to count the tonne, which is a different
    -- question from how many there are, and one the product could not answer.
    CREATE TABLE authorisations (
        id                  TEXT PRIMARY KEY,
        project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        authority           TEXT NOT NULL,
        reference           TEXT NOT NULL,
        issued_on           TEXT NOT NULL,
        authorised_use      TEXT NOT NULL,
        authorised_volume_t REAL NOT NULL,
        ca_committed        INTEGER NOT NULL,
        first_vintage       INTEGER NOT NULL,
        last_vintage        INTEGER NOT NULL,
        valid_until         TEXT,
        revoked_on          TEXT,
        created_at          TEXT NOT NULL,
        UNIQUE(project_id, reference)
    );
    CREATE INDEX idx_auth_project ON authorisations(project_id);

    -- The adjustment itself, kept apart from the letter that promised it.
    -- The gap between the two is where double claiming actually lives.
    CREATE TABLE corresponding_adjustments (
        id               TEXT PRIMARY KEY,
        authorisation_id TEXT NOT NULL REFERENCES authorisations(id) ON DELETE CASCADE,
        project_id       TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        vintage_year     INTEGER NOT NULL,
        volume_t         REAL NOT NULL,
        applied_on       TEXT NOT NULL,
        reported_in      TEXT NOT NULL,
        created_at       TEXT NOT NULL
    );
    CREATE INDEX idx_ca_project ON corresponding_adjustments(project_id, vintage_year);
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
