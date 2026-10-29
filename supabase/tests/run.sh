#!/usr/bin/env bash
# Load the migrations into a scratch database and run the access-control tests.
#
#   PGHOST=... PGPORT=... PGUSER=postgres supabase/tests/run.sh
#
# Needs a plain Postgres 15+ superuser connection. It creates and drops a
# database called carbonstack_rls_test; it never touches any other database.
# The storage migration is skipped: it needs Supabase's storage schema.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
db=carbonstack_rls_test

psql -q -v ON_ERROR_STOP=1 -d postgres -c "drop database if exists $db" -c "create database $db"
trap 'psql -q -d postgres -c "drop database if exists $db"' EXIT

psql -q -v ON_ERROR_STOP=1 -d "$db" -f "$here/auth_stub.sql"
psql -q -v ON_ERROR_STOP=1 -d "$db" -f "$here/../migrations/20261029000001_core.sql"
psql -q -o /dev/null -v ON_ERROR_STOP=1 -d "$db" -f "$here/rls_test.sql"
