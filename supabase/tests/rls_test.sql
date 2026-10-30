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

-- ---------------------------------------------------------------------------
-- Claims and retirement (migration 0003). The 2025 vintage is issued with
-- serials 1-10.
-- ---------------------------------------------------------------------------

-- Only owners and admins retire, and never more than was issued.
select test.login('00000000-0000-0000-0000-00000000000c');
select test.expect_error($q$
  select public.retire_credits((select v from test.ids where k = 'vintage'), 1, 'Acme Foods', 'contribution')$q$,
  'only owners and admins');

select test.login('00000000-0000-0000-0000-00000000000a');
-- No authorisation yet, so nothing may be retired as an offset.
select test.expect_error($q$
  select public.retire_credits((select v from test.ids where k = 'vintage'), 1, 'Acme Foods', 'offset')$q$,
  'only 0 credits of this vintage have a corresponding adjustment');
select test.expect_count($q$
  select * from public.retire_credits((select v from test.ids where k = 'vintage'), 4, 'Acme Foods', 'contribution')
  where serial_start = 1 and serial_end = 4 and claim ilike '%may not be counted against%'$q$, 1);

-- A letter that commits to an adjustment is still not an adjustment.
with a as (
  insert into public.authorisations (org_id, project_id, authority, reference, issued_on, authorised_use,
                                     authorised_volume_t, adjustment_committed, first_vintage, last_vintage)
  values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'project'),
          'MoEFCC', 'LoA/2026/001', '2026-01-10', 'corsia', 100, true, 2025, 2026)
  returning id)
insert into test.ids select 'auth', id from a;
select test.expect_error($q$
  select public.retire_credits((select v from test.ids where k = 'vintage'), 1, 'Air Co', 'corsia')$q$,
  'only 0 credits');

-- 3.5 t adjusted: three whole credits may be offsets, no more.
insert into public.adjustments (org_id, authorisation_id, vintage_year, volume_t, reported_on, reference)
values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'auth'), 2025, 3.5,
        '2026-03-01', 'BTR/2026/IN/7');
select test.expect_error($q$
  select public.retire_credits((select v from test.ids where k = 'vintage'), 4, 'Air Co', 'offset')$q$,
  'only 3 credits of this vintage have a corresponding adjustment');
select test.expect_count($q$
  select * from public.retire_credits((select v from test.ids where k = 'vintage'), 3, 'Air Co', 'corsia')
  where serial_start = 5 and serial_end = 7$q$, 1);
select test.expect_error($q$
  select public.retire_credits((select v from test.ids where k = 'vintage'), 1, 'Air Co', 'offset')$q$,
  'only 0 credits');
select test.expect_error($q$
  select public.retire_credits((select v from test.ids where k = 'vintage'), 4, 'Acme Foods', 'contribution')$q$,
  'only 3 credits of this vintage are left');
select public.retire_credits((select v from test.ids where k = 'vintage'), 3, 'Acme Foods', 'contribution');
select test.expect_error($q$
  select public.retire_credits((select v from test.ids where k = 'vintage'), 1, 'Acme Foods', 'contribution')$q$,
  'only 0 credits');
-- Draft vintages cannot be retired.
select test.expect_error($q$
  select public.retire_credits((select v from test.ids where k = 'vintage2'), 1, 'X Co', 'contribution')$q$,
  'only issued credits');

-- Retirements cannot be written, edited or deleted directly.
select test.expect_error($q$
  insert into public.retirements (org_id, vintage_id, serial_start, serial_end, beneficiary, purpose, claim)
  values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'vintage'), 50, 60,
          'Forged', 'offset', 'x')$q$, 'row-level security');
delete from public.retirements;
select test.expect_count('select * from public.retirements', 3);

select test.expect_count($q$select * from public.vintage_claims((select v from test.ids where k = 'acme'))
  where (basis->>'offsettable_credits')::int = 3 and (basis->>'offset_remaining')::int = 0$q$, 1);

-- Bilal is a viewer at Acme: he can read retirements, not make them or authorise.
select test.login('00000000-0000-0000-0000-00000000000b');
select test.expect_count('select * from public.retirements', 3);
select test.expect_error($q$
  select public.retire_credits((select v from test.ids where k = 'vintage'), 1, 'B', 'contribution')$q$,
  'only owners and admins');
select test.expect_error($q$
  insert into public.adjustments (org_id, authorisation_id, vintage_year, volume_t, reported_on, reference)
  values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'auth'), 2025, 50,
          '2026-03-02', 'fake')$q$, 'row-level security');

-- Anyone can verify a credit, signed in or not, and sees registry facts only.
select test.login(null);
select test.expect_error('select * from public.retirements', 'permission denied');
create temp table verified as
select public.verify_credit(public_code) as j from (
  select upper(substr(replace((select v from test.ids where k = 'acme')::text, '-', ''), 1, 8))
         || '-2025-6' as public_code) c;
do $$
declare j jsonb := (select j from verified);
begin
  if not (j->>'found')::boolean then raise exception 'credit 6 not found: %', j; end if;
  if j->'retirement'->>'purpose' <> 'corsia' or j->'retirement'->>'beneficiary' <> 'Air Co' then
    raise exception 'credit 6 should be retired for CORSIA by Air Co: %', j;
  end if;
  if j::text ~* 'murugan|lakshmi|payout|phone' then
    raise exception 'public verification leaked farmer data: %', j;
  end if;
  if (j->'vintage'->'claim_basis'->>'offsettable_credits')::int <> 3 then
    raise exception 'expected 3 offsettable credits: %', j;
  end if;
end $$;
select test.expect_count($q$select 1 where (public.verify_credit('00000000-2025-6')->>'found')::boolean$q$, 0);
select test.expect_count($q$select 1 where (public.verify_credit('nonsense')->>'found')::boolean$q$, 0);
select test.expect_count($q$select 1 where (public.retirement_certificate(gen_random_uuid())->>'found')::boolean$q$, 0);
do $$
declare c jsonb := public.retirement_certificate(((select j from verified)->'retirement'->>'id')::uuid);
begin
  if not (c->>'found')::boolean or (c->>'quantity')::int <> 3 or c->'vintage'->>'vintage_year' <> '2025' then
    raise exception 'certificate lookup failed: %', c;
  end if;
end $$;


-- ===========================================================================
-- 0004: logger uploads, registry references, statement links
-- ===========================================================================

-- Dev (field agent) uploads a logger file for Acme's farm and shares Murugan's statement.
select test.login('00000000-0000-0000-0000-00000000000d');
insert into public.sensor_uploads (org_id, farm_id, file_name, readings, summary, uploaded_by)
values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'farm'),
        'WL-1.csv', 288, '{"records": []}', '00000000-0000-0000-0000-00000000000d');
select test.expect_error($q$
  insert into public.sensor_uploads (org_id, farm_id, file_name, readings, summary, uploaded_by)
  values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'farm'),
          'x.csv', 1, '{}', '00000000-0000-0000-0000-00000000000a')$q$, 'row-level security');
with r as (
  insert into public.statement_links (org_id, farmer_id, language, created_by)
  values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'farmer'), 'ta',
          '00000000-0000-0000-0000-00000000000d')
  returning id)
insert into test.ids select 'link', id from r;
-- A link cannot run for more than a year, nor be edited, only revoked.
select test.expect_error($q$
  insert into public.statement_links (org_id, farmer_id, created_by, expires_at)
  values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'farmer'),
          '00000000-0000-0000-0000-00000000000d', now() + interval '2 years')$q$, 'check constraint');
select test.expect_error($q$
  update public.statement_links set expires_at = now() + interval '200 days'
  where id = (select v from test.ids where k = 'link')$q$, 'row-level security|only be revoked');
-- Field agents cannot record registry references.
select test.expect_error($q$
  select public.set_registry_reference((select v from test.ids where k = 'vintage'), 'VCS-1')$q$,
  'only owners and admins');

-- Bilal is a viewer at Acme: he reads uploads, cannot add them or share statements.
select test.login('00000000-0000-0000-0000-00000000000b');
select test.expect_count('select * from public.sensor_uploads', 1);
select test.expect_error($q$
  insert into public.statement_links (org_id, farmer_id, created_by)
  values ((select v from test.ids where k = 'acme'), (select v from test.ids where k = 'farmer'),
          '00000000-0000-0000-0000-00000000000b')$q$, 'row-level security');
-- Other Co's link cannot point at Acme's farmer.
select test.expect_error($q$
  insert into public.statement_links (org_id, farmer_id, created_by)
  values ((select v from test.ids where k = 'other'), (select v from test.ids where k = 'farmer'),
          '00000000-0000-0000-0000-00000000000b')$q$, 'another organisation');

-- Asha records the registry's id for the issued vintage; not for a draft.
select test.login('00000000-0000-0000-0000-00000000000a');
select public.set_registry_reference((select v from test.ids where k = 'vintage'), ' VCS-5123-2025 ');
select test.expect_count($q$select * from public.vintages where registry_ref = 'VCS-5123-2025'$q$, 1);
select test.expect_error($q$
  select public.set_registry_reference((select v from test.ids where k = 'vintage2'), 'VCS-9')$q$,
  'only an issued vintage');
create temp table link_token as
  select token from public.statement_links where id = (select v from test.ids where k = 'link');
grant select on link_token to anon, authenticated;

-- The farmer opens the statement without an account and sees only their own record.
select test.login(null);
select test.expect_error('select * from public.statement_links', 'permission denied');
select test.expect_error('select * from public.sensor_uploads', 'permission denied');
do $$
declare j jsonb := public.farmer_statement((select token from link_token));
begin
  if not (j->>'found')::boolean or j->'farmer'->>'name' <> 'Murugan' or j->>'language' <> 'ta' then
    raise exception 'statement lookup failed: %', j;
  end if;
  if jsonb_array_length(j->'farms') <> 1 then
    raise exception 'expected Murugan''s one farm: %', j;
  end if;
  if j::text ~* 'boundary|centroid|payout_reference|"phone"|consent_reference' then
    raise exception 'statement leaked more than the farmer''s own summary: %', j;
  end if;
end $$;
select test.expect_count($q$select 1 where (public.farmer_statement('nonsense')->>'found')::boolean$q$, 0);
select test.expect_count($q$select 1 where (public.farmer_statement(repeat('a', 64))->>'found')::boolean$q$, 0);

-- Revoked, it is gone.
select test.login('00000000-0000-0000-0000-00000000000d');
update public.statement_links set revoked_at = now() where id = (select v from test.ids where k = 'link');
select test.expect_error($q$
  update public.statement_links set revoked_at = null where id = (select v from test.ids where k = 'link')$q$,
  'row-level security|only be revoked');
select test.login(null);
select test.expect_count($q$select 1 where (public.farmer_statement((select token from link_token))->>'found')::boolean$q$, 0);

reset role;
\echo 'rls tests passed'
