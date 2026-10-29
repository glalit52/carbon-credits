-- The parts of Supabase's auth schema the migrations depend on, so they can
-- be tested on a plain Postgres. Not used in a real Supabase project.

-- Roles are cluster-wide, so a previous run may already have created them.
do $$
declare r text;
begin
  foreach r in array array['anon', 'authenticated', 'service_role'] loop
    if not exists (select 1 from pg_roles where rolname = r) then
      execute format('create role %I nologin', r);
    end if;
  end loop;
end $$;
alter role service_role bypassrls;

create schema auth;
grant usage on schema auth to anon, authenticated;

create table auth.users (
  id                  uuid primary key,
  email               text,
  phone               text,
  raw_user_meta_data  jsonb default '{}'::jsonb
);

create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;
grant execute on function auth.uid() to anon, authenticated;

grant usage on schema public to anon, authenticated;
alter default privileges in schema public grant all on tables to anon, authenticated;
alter default privileges in schema public grant all on sequences to anon, authenticated;
