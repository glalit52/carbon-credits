-- Grant table, sequence and routine access to authenticated and service_role in public schema.
-- Row-level security (RLS) on each table controls which specific rows the authenticated user can see/modify.

grant usage on schema public to anon, authenticated, service_role;

grant all on all tables in schema public to authenticated, service_role;
grant all on all sequences in schema public to authenticated, service_role;
grant all on all routines in schema public to authenticated, service_role;

alter default privileges in schema public grant all on tables to authenticated, service_role;
alter default privileges in schema public grant all on sequences to authenticated, service_role;
alter default privileges in schema public grant all on routines to authenticated, service_role;
