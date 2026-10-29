-- Access-control tests for the core migration. Run with
-- supabase/tests/run.sh, which loads auth_stub.sql and the migrations into a
-- scratch database first. Any failed expectation raises and stops the run.

\set ON_ERROR_STOP on

create schema test;
grant usage on schema test to anon, authenticated;

-- Act as a signed-in user (or anon when uid is null) for what follows.
create function test.login(uid uuid) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claim.sub', coalesce(uid::text, ''), false);
  if uid is null then
    execute 'set role anon';
  else
    execute 'set role authenticated';
  end if;
end;
$$;

create function test.expect_error(stmt text, pattern text) returns void
language plpgsql as $$
begin
  begin
    execute stmt;
  exception when others then
    if sqlerrm !~* pattern then
      raise exception 'expected error matching "%", got "%" from: %', pattern, sqlerrm, stmt;
    end if;
    return;
  end;
  raise exception 'expected an error matching "%" but it succeeded: %', pattern, stmt;
end;
$$;

create function test.expect_count(stmt text, expected bigint) returns void
language plpgsql as $$
declare n bigint;
begin
  execute format('select count(*) from (%s) q', stmt) into n;
  if n <> expected then
    raise exception 'expected % row(s), got %: %', expected, n, stmt;
  end if;
end;
$$;

grant execute on all functions in schema test to anon, authenticated;
grant all on schema test to anon, authenticated;
create table test.ids (k text primary key, v uuid);
grant all on test.ids to anon, authenticated;

-- People. Signing up creates the profile through the trigger.
insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-0000-0000-00000000000a', 'asha@acme.test',   '{"full_name":"Asha"}'),
  ('00000000-0000-0000-0000-00000000000b', 'bilal@other.test', '{"full_name":"Bilal"}'),
  ('00000000-0000-0000-0000-00000000000c', 'chen@acme.test',   '{"full_name":"Chen"}'),
  ('00000000-0000-0000-0000-00000000000d', 'dev@acme.test',    '{"full_name":"Dev"}'),
  ('00000000-0000-0000-0000-00000000000e', 'esi@acme.test',    '{"full_name":"Esi"}');

do $$ begin
  if (select count(*) from public.profiles) <> 5 then
    raise exception 'profiles were not created on sign-up';
  end if;
end $$;

-- Asha creates Acme; Bilal creates Other.
select test.login('00000000-0000-0000-0000-00000000000a');
insert into test.ids values ('acme', public.create_organization('Acme Carbon', 'developer', 'India'));
select test.login('00000000-0000-0000-0000-00000000000b');
insert into test.ids values ('other', public.create_organization('Other Co'));

-- Anonymous callers see nothing and cannot create organisations.
select test.login(null);
select test.expect_error('select * from public.farms', 'permission denied');
select test.expect_error($q$select public.create_organization('x')$q$, 'permission denied');

-- Asha adds a project, a farmer and a farm.
select test.login('00000000-0000-0000-0000-00000000000a');
with r as (
  insert into public.projects (org_id, name, pathway, methodology)
  values ((select v from test.ids where k = 'acme'), 'Cauvery AWD', 'rice', 'VM0051')
  returning id)
insert into test.ids select 'project', id from r;
with r as (
  insert into public.farmers (org_id, name, village)
  values ((select v from test.ids where k = 'acme'), 'Murugan', 'Vallam')
  returning id)
insert into test.ids select 'farmer', id from r;
with r as (
  insert into public.farms (org_id, project_id, farmer_id, name, boundary, area_ha,
                            centroid_lat, centroid_lon)
  values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'project'),
          (select v from test.ids where k = 'farmer'), 'Plot 1',
          '{"type":"Polygon","coordinates":[[[79.13,10.78],[79.14,10.78],[79.14,10.79],[79.13,10.78]]]}',
          2.4, 10.785, 79.135)
  returning id)
insert into test.ids select 'farm', id from r;

-- Bilal cannot see Acme's data, nor write into Acme.
select test.login('00000000-0000-0000-0000-00000000000b');
select test.expect_count('select * from public.farms', 0);
select test.expect_count('select * from public.farmers', 0);
select test.expect_count('select * from public.organizations', 1);
select test.expect_error($q$
  insert into public.farmers (org_id, name)
  values ((select v from test.ids where k = 'acme'), 'Intruder')$q$, 'row-level security');
-- ...nor attach Acme's farmer to a farm in his own organisation.
select test.expect_error($q$
  insert into public.farms (org_id, farmer_id, name, boundary, area_ha, centroid_lat, centroid_lon)
  values ((select v from test.ids where k = 'other'), (select v from test.ids where k = 'farmer'),
          'Stolen', '{"type":"Polygon","coordinates":[]}', 1, 0, 0)$q$, 'another organisation');
-- Updates to rows he cannot see change nothing.
update public.farms set name = 'renamed';
select test.login('00000000-0000-0000-0000-00000000000a');
select test.expect_count($q$select * from public.farms where name = 'Plot 1'$q$, 1);

-- Asha adds Chen (analyst), Dev (field agent) and Esi (reviewer).
insert into public.memberships (org_id, user_id, role) values
  ((select v from test.ids where k = 'acme'), '00000000-0000-0000-0000-00000000000c', 'analyst'),
  ((select v from test.ids where k = 'acme'), '00000000-0000-0000-0000-00000000000d', 'field_agent'),
  ((select v from test.ids where k = 'acme'), '00000000-0000-0000-0000-00000000000e', 'reviewer');

-- The field agent enrols farmers but cannot create projects or vintages,
-- and cannot promote himself.
select test.login('00000000-0000-0000-0000-00000000000d');
insert into public.farmers (org_id, name) values ((select v from test.ids where k = 'acme'), 'Lakshmi');
select test.expect_error($q$
  insert into public.projects (org_id, name, pathway, methodology)
  values ((select v from test.ids where k = 'acme'), 'Nope', 'rice', 'VM0051')$q$, 'row-level security');
update public.memberships set role = 'owner' where user_id = '00000000-0000-0000-0000-00000000000d';
select test.expect_count($q$select * from public.memberships
  where user_id = '00000000-0000-0000-0000-00000000000d' and role = 'field_agent'$q$, 1);

-- Bad data is refused by the table itself.
select test.expect_error($q$
  insert into public.farms (org_id, name, boundary, area_ha, centroid_lat, centroid_lon)
  values ((select v from test.ids where k = 'acme'), 'Point', '{"type":"Point","coordinates":[0,0]}',
          1, 0, 0)$q$, 'check constraint');
select test.expect_error($q$
  insert into public.farms (org_id, name, boundary, area_ha, centroid_lat, centroid_lon)
  values ((select v from test.ids where k = 'acme'), 'Zero', '{"type":"Polygon","coordinates":[]}',
          0, 0, 0)$q$, 'check constraint');

-- Vintage review. Chen drafts and submits; Chen may not approve his own.
select test.login('00000000-0000-0000-0000-00000000000c');
with r as (
  insert into public.vintages (org_id, project_id, year, gross_t, net_t, issuable)
  values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'project'),
          2025, 12.5, 10.2, 10)
  returning id)
insert into test.ids select 'vintage', id from r;
select test.expect_error($q$
  insert into public.vintages (org_id, project_id, year, status)
  values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'project'),
          2026, 'approved')$q$, 'row-level security');
select public.transition_vintage((select v from test.ids where k = 'vintage'), 'submitted');
-- A plain update cannot skip review.
update public.vintages set status = 'issued';
select test.expect_count($q$select * from public.vintages where status = 'submitted'$q$, 1);
select test.expect_error($q$
  select public.transition_vintage((select v from test.ids where k = 'vintage'), 'approved')$q$,
  'not allowed to review');

-- Esi reviews: a hold needs a reason; then approval.
select test.login('00000000-0000-0000-0000-00000000000e');
select test.expect_error($q$
  select public.transition_vintage((select v from test.ids where k = 'vintage'), 'on_hold')$q$,
  'say why');
select public.transition_vintage((select v from test.ids where k = 'vintage'), 'approved', 'checked');
select test.expect_error($q$
  select public.transition_vintage((select v from test.ids where k = 'vintage'), 'issued')$q$,
  'not allowed to issue');

-- An owner who submitted cannot approve alone either.
select test.login('00000000-0000-0000-0000-00000000000a');
with r as (
  insert into public.vintages (org_id, project_id, year, net_t, issuable)
  values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'project'),
          2026, 3.9, 3)
  returning id)
insert into test.ids select 'vintage2', id from r;
select public.transition_vintage((select v from test.ids where k = 'vintage2'), 'submitted');
select test.expect_error($q$
  select public.transition_vintage((select v from test.ids where k = 'vintage2'), 'approved')$q$,
  'second person');

-- Asha issues the approved vintage: serials 1..10.
select public.transition_vintage((select v from test.ids where k = 'vintage'), 'issued');
select test.expect_count($q$select * from public.vintages
  where status = 'issued' and serial_start = 1 and serial_end = 10$q$, 1);
select test.expect_count($q$select * from public.vintage_events$q$, 4);

-- Bilal cannot move Acme's vintage.
select test.login('00000000-0000-0000-0000-00000000000b');
select test.expect_error($q$
  select public.transition_vintage((select v from test.ids where k = 'vintage2'), 'approved')$q$,
  'not found');

-- Invitations: only to the address they were sent to.
select test.login('00000000-0000-0000-0000-00000000000a');
insert into public.invitations (org_id, email, role, token)
values ((select v from test.ids where k = 'acme'), 'bilal@other.test', 'viewer', 'tok-bilal'),
       ((select v from test.ids where k = 'acme'), 'someone@else.test', 'admin', 'tok-else');
select test.login('00000000-0000-0000-0000-00000000000b');
select test.expect_error($q$select public.accept_invitation('tok-else')$q$, 'different email');
select test.expect_count('select * from public.invitations', 0);
select public.accept_invitation('tok-bilal');
select test.expect_count('select * from public.farms', 1);
select test.expect_count('select * from public.organizations', 2);
-- ...as a viewer, who can read but not write.
select test.expect_error($q$
  insert into public.farmers (org_id, name)
  values ((select v from test.ids where k = 'acme'), 'Viewer write')$q$, 'row-level security');
select test.expect_error($q$select public.accept_invitation('tok-bilal')$q$, 'invalid or has expired');

-- Every change above was audited, and nobody can write the audit log.
select test.login('00000000-0000-0000-0000-00000000000a');
select test.expect_count($q$select * from public.audit_events where entity = 'farms'$q$, 1);
select test.expect_count($q$select * from public.audit_events where entity = 'vintages'$q$, 6);
select test.expect_error($q$
  insert into public.audit_events (org_id, action, entity)
  values ((select v from test.ids where k = 'acme'), 'forged', 'farms')$q$, 'row-level security');
create temp table audit_before as select count(*) as n from public.audit_events;
delete from public.audit_events;
update public.audit_events set action = 'rewritten';
do $$ begin
  if (select count(*) from public.audit_events) <> (select n from audit_before)
     or exists (select 1 from public.audit_events where action = 'rewritten') then
    raise exception 'the audit log was altered';
  end if;
end $$;

reset role;
\echo 'rls tests passed'
