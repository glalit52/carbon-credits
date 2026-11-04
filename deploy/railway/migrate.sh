#!/bin/sh
# Brings the Railway Postgres up to date, then exits. Runs as its own service
# on every deploy:
#   1. bootstrap.sql: roles and the auth schema (idempotent)
#   2. waits for the auth service to create auth.users
#   3. applies supabase/migrations/*.sql not yet recorded, each in one
#      transaction; the storage one waits for the storage service's schema
#   4. takes back the superuser grant storage-api gives `authenticator`
#   5. tells PostgREST to reload its schema cache
# With RUN_RLS_TESTS=1 it then runs supabase/tests on a scratch database.
set -eu

: "${PGHOST:?}" "${PGUSER:?}" "${PGPASSWORD:?}" "${PGDATABASE:?}"
: "${AUTHENTICATOR_PASSWORD:?}" "${AUTH_ADMIN_PASSWORD:?}"
export PGPORT="${PGPORT:-5432}"

sql() { psql -X -q -v ON_ERROR_STOP=1 "$@"; }
yes_no() { psql -X -At -v ON_ERROR_STOP=1 -c "$1"; }

wait_for() { # <sql returning t/f> <what> <seconds>
  waited=0
  until [ "$(yes_no "$1")" = t ]; do
    if [ "$waited" -ge "$3" ]; then echo "gave up waiting for $2 after ${3}s" >&2; exit 1; fi
    echo "waiting for $2..."
    sleep 5
    waited=$((waited + 5))
  done
}

wait_for "select true" "postgres" 300

echo "bootstrap: roles and the auth schema"
sql -v authenticator_password="$AUTHENTICATOR_PASSWORD" -v auth_admin_password="$AUTH_ADMIN_PASSWORD" \
    -f /deploy/bootstrap.sql

wait_for "select to_regclass('auth.users') is not null" "the auth service to create auth.users" 600

sql -c "create schema if not exists supabase_migrations;
        create table if not exists supabase_migrations.schema_migrations (
          version text primary key, applied_at timestamptz not null default now());"

for file in /supabase/migrations/*.sql; do
  version="$(basename "$file" .sql)"
  if [ "$(yes_no "select exists (select 1 from supabase_migrations.schema_migrations where version = '$version')")" = t ]; then
    continue
  fi
  case "$version" in
    *_storage) wait_for "select to_regclass('storage.objects') is not null" "the storage service to create storage.objects" 600 ;;
  esac
  echo "applying $version"
  { cat "$file"; printf "\ninsert into supabase_migrations.schema_migrations (version) values ('%s');\n" "$version"; } \
    | sql -1
done

# storage-api's first migration runs `grant postgres to authenticator`.
# PostgREST never needs it, and with it a token naming role "postgres" would be a superuser.
sql -c "do \$\$ begin
          if pg_has_role('authenticator', 'postgres', 'member') then revoke postgres from authenticator; end if;
        end \$\$;"
sql -c "notify pgrst, 'reload schema';"
echo "database is up to date"

if [ "${RUN_RLS_TESTS:-0}" = 1 ]; then
  echo "running row-level security tests on a scratch database"
  bash /supabase/tests/run.sh
fi
