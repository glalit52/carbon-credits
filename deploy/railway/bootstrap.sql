-- What a Supabase project has before any migration runs, on a plain Postgres:
-- the API roles, the login PostgREST connects as, and a schema the auth
-- service owns and migrates itself. Idempotent; migrate.sh runs it on every
-- deploy with the two passwords as psql variables.

-- Extensions live in their own schema, as on Supabase, so the core
-- migration's `revoke execute on all functions in schema public` cannot
-- reach them (it would take gen_random_bytes, the invitation token default,
-- away from signed-in users).
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
do $$
begin
  -- The first bootstrap installed it in public; move it, keeping every default bound to it.
  if (select n.nspname from pg_extension e join pg_namespace n on n.oid = e.extnamespace
      where e.extname = 'pgcrypto') <> 'extensions' then
    alter extension pgcrypto set schema extensions;
  end if;
end $$;
select format('alter database %I set search_path to "$user", public, extensions', current_database()) \gexec

do $$
begin
  if not exists (select from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
  if not exists (select from pg_roles where rolname = 'authenticator') then
    create role authenticator login noinherit;
  end if;
  if not exists (select from pg_roles where rolname = 'supabase_auth_admin') then
    create role supabase_auth_admin login noinherit createrole;
  end if;
end $$;

alter role service_role bypassrls;
alter role authenticator with login noinherit password :'authenticator_password';
alter role supabase_auth_admin with login noinherit createrole password :'auth_admin_password';

-- PostgREST logs in as authenticator and switches to the role in the JWT.
grant anon, authenticated, service_role to authenticator;

-- The auth service creates and migrates everything in here itself.
create schema if not exists auth authorization supabase_auth_admin;
alter role supabase_auth_admin set search_path = auth;
select format('grant create on database %I to supabase_auth_admin', current_database()) \gexec
-- Policies call auth.uid().
grant usage on schema auth to anon, authenticated, service_role;

grant usage on schema extensions to anon, authenticated, service_role;
grant execute on all functions in schema extensions to anon, authenticated, service_role;

-- Supabase's defaults for the public schema. The core migration then takes
-- anon's table access away again, explicitly.
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
