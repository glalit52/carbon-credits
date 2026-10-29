-- Core schema for the carbonstack web app.
--
-- Everything a customer owns hangs off an organisation, and every table is
-- protected by row-level security keyed on membership of that organisation.
-- The browser talks to Postgres directly through Supabase with the user's own
-- JWT, so these policies ARE the access control: there is no server in front
-- of them that could be relied on to filter instead.
--
-- Boundaries are stored as GeoJSON (jsonb) rather than PostGIS geometry so the
-- schema runs on any Postgres. Area and centroid are computed by the app and
-- checked here for plausibility; PostGIS can be added later without changing
-- the API.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Organisations, people and roles
-- ---------------------------------------------------------------------------

create table public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  full_name   text,
  phone       text,
  created_at  timestamptz not null default now()
);

create table public.organizations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null check (length(trim(name)) between 2 and 120),
  kind        text not null default 'developer'
              check (kind in ('developer', 'aggregator', 'buyer', 'verifier')),
  country     text,
  created_by  uuid references auth.users (id) on delete set null,
  created_at  timestamptz not null default now()
);

-- owner      everything, including deleting the organisation's members
-- admin      everything except changing owners
-- reviewer   approves or holds vintages; cannot approve their own submission
-- analyst    projects, estimates, imports, submits vintages
-- field_agent  enrols farmers and farms, records practices and soil samples
-- viewer     read-only
create table public.memberships (
  org_id      uuid not null references public.organizations (id) on delete cascade,
  user_id     uuid not null references auth.users (id) on delete cascade,
  role        text not null
              check (role in ('owner', 'admin', 'reviewer', 'analyst', 'field_agent', 'viewer')),
  created_at  timestamptz not null default now(),
  primary key (org_id, user_id)
);
create index memberships_user_idx on public.memberships (user_id);

create table public.invitations (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references public.organizations (id) on delete cascade,
  email       text not null check (position('@' in email) > 1),
  role        text not null
              check (role in ('admin', 'reviewer', 'analyst', 'field_agent', 'viewer')),
  token       text not null unique default encode(gen_random_bytes(24), 'hex'),
  invited_by  uuid references auth.users (id) on delete set null,
  accepted_at timestamptz,
  expires_at  timestamptz not null default now() + interval '14 days',
  created_at  timestamptz not null default now()
);
create index invitations_org_idx on public.invitations (org_id);

-- ---------------------------------------------------------------------------
-- Access helpers. SECURITY DEFINER so policies on memberships can call them
-- without recursing into memberships' own policies.
-- ---------------------------------------------------------------------------

create or replace function public.is_member(target_org uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.memberships
    where org_id = target_org and user_id = auth.uid());
$$;

create or replace function public.has_role(target_org uuid, roles text[])
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.memberships
    where org_id = target_org and user_id = auth.uid() and role = any (roles));
$$;

-- Roles allowed to write field data, project data and money, respectively.
create or replace function public.can_enrol(target_org uuid)
returns boolean language sql stable as $$
  select public.has_role(target_org, array['owner', 'admin', 'analyst', 'field_agent']);
$$;

create or replace function public.can_manage(target_org uuid)
returns boolean language sql stable as $$
  select public.has_role(target_org, array['owner', 'admin', 'analyst']);
$$;

create or replace function public.can_administer(target_org uuid)
returns boolean language sql stable as $$
  select public.has_role(target_org, array['owner', 'admin']);
$$;

-- ---------------------------------------------------------------------------
-- Projects, farmers, farms
-- ---------------------------------------------------------------------------

create table public.projects (
  id                    uuid primary key default gen_random_uuid(),
  org_id                uuid not null references public.organizations (id) on delete cascade,
  name                  text not null check (length(trim(name)) between 2 and 160),
  pathway               text not null
                        check (pathway in ('rice', 'agroforestry', 'soil', 'other')),
  methodology           text not null,          -- e.g. VM0051, VM0047, VM0042
  registry              text,                   -- Verra, Gold Standard, ...
  country               text,
  region                text,
  start_date            date,
  crediting_period_yrs  int check (crediting_period_yrs between 1 and 100),
  status                text not null default 'design'
                        check (status in ('design', 'listed', 'registered', 'closed')),
  created_by            uuid references auth.users (id) on delete set null,
  created_at            timestamptz not null default now()
);
create index projects_org_idx on public.projects (org_id);

create table public.farmers (
  id                    uuid primary key default gen_random_uuid(),
  org_id                uuid not null references public.organizations (id) on delete cascade,
  name                  text not null check (length(trim(name)) between 1 and 160),
  phone                 text,
  village               text,
  district              text,
  state                 text,
  country               text,
  external_ref          text,                   -- the customer's own farmer id
  consent_on            date,
  consent_reference     text,
  carbon_rights_ref     text,
  carbon_rights_signed_on date,
  payout_method         text check (payout_method in ('bank', 'upi', 'mobile_money', 'cash', 'other')),
  payout_reference      text,                   -- masked handle, never full account numbers
  created_by            uuid references auth.users (id) on delete set null,
  created_at            timestamptz not null default now(),
  unique (org_id, external_ref)
);
create index farmers_org_idx on public.farmers (org_id);

create table public.farms (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references public.organizations (id) on delete cascade,
  project_id        uuid references public.projects (id) on delete set null,
  farmer_id         uuid references public.farmers (id) on delete set null,
  name              text not null check (length(trim(name)) between 1 and 160),
  external_ref      text,
  boundary          jsonb not null
                    check (boundary->>'type' in ('Polygon', 'MultiPolygon')),
  area_ha           numeric(12, 4) not null check (area_ha > 0 and area_ha < 100000),
  centroid_lat      double precision not null check (centroid_lat between -90 and 90),
  centroid_lon      double precision not null check (centroid_lon between -180 and 180),
  crop              text,
  practice          text,                       -- awd, agroforestry, cover_crop, ...
  -- Same vocabularies as carbonstack.domain, so a farm passes straight to the engine.
  tenure            text check (tenure in ('owned_title', 'registered_lease', 'community_right',
                                           'grama_sabha_consent', 'undocumented')),
  tenure_reference  text,
  rice_ecosystem    text check (rice_ecosystem in ('irrigated_lowland', 'rainfed', 'upland',
                                                   'deepwater', 'unknown')),
  water_control     text check (water_control in ('full', 'irrigation_only', 'none', 'unknown')),
  stems_planted     int check (stems_planted >= 0),
  species           text[],
  enrolled_on       date,
  -- Crop calendar the engine needs. Months 1-12; a season may wrap the year.
  seasons           jsonb not null default '[]'::jsonb,
  source            text not null default 'drawn'
                    check (source in ('drawn', 'uploaded', 'imported', 'gps', 'api')),
  status            text not null default 'enrolled'
                    check (status in ('draft', 'enrolled', 'blocked', 'withdrawn')),
  created_by        uuid references auth.users (id) on delete set null,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (org_id, external_ref)
);
create index farms_org_idx on public.farms (org_id);
create index farms_project_idx on public.farms (project_id);
create index farms_farmer_idx on public.farms (farmer_id);

create table public.practice_records (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references public.organizations (id) on delete cascade,
  farm_id       uuid not null references public.farms (id) on delete cascade,
  year          int not null check (year between 1990 and 2100),
  season        text,
  practice      text not null,
  started_on    date,
  ended_on      date check (ended_on is null or started_on is null or ended_on >= started_on),
  evidence_path text,                           -- object in the 'evidence' bucket
  notes         text,
  recorded_by   uuid references auth.users (id) on delete set null,
  created_at    timestamptz not null default now()
);
create index practice_records_farm_idx on public.practice_records (farm_id);

create table public.soil_samples (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references public.organizations (id) on delete cascade,
  farm_id          uuid not null references public.farms (id) on delete cascade,
  sampled_on       date not null,
  depth_top_cm     numeric(6, 1) not null check (depth_top_cm >= 0),
  depth_bottom_cm  numeric(6, 1) not null,
  soc_pct          numeric(6, 3) not null check (soc_pct >= 0 and soc_pct < 60),
  bulk_density     numeric(5, 3) check (bulk_density > 0 and bulk_density < 3),
  lab              text,
  lab_reference    text,
  recorded_by      uuid references auth.users (id) on delete set null,
  created_at       timestamptz not null default now(),
  check (depth_bottom_cm > depth_top_cm)
);
create index soil_samples_farm_idx on public.soil_samples (farm_id);

-- ---------------------------------------------------------------------------
-- Imports, estimates, credits and money
-- ---------------------------------------------------------------------------

create table public.imports (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references public.organizations (id) on delete cascade,
  kind         text not null check (kind in ('farms', 'farmers', 'practices', 'soil')),
  filename     text,
  row_count    int not null default 0,
  ok_count     int not null default 0,
  error_count  int not null default 0,
  errors       jsonb not null default '[]'::jsonb,
  created_by   uuid references auth.users (id) on delete set null,
  created_at   timestamptz not null default now()
);
create index imports_org_idx on public.imports (org_id);

-- One engine run for one farm. Input and result are kept whole so any number
-- on a dashboard can be traced back to what produced it.
create table public.estimates (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references public.organizations (id) on delete cascade,
  farm_id         uuid not null references public.farms (id) on delete cascade,
  year            int not null,
  methodology     text not null,
  gross_t         numeric(14, 4) not null,
  net_t           numeric(14, 4) not null,
  data_quality    text not null,               -- e.g. 'simulated', 'live-climate'
  input           jsonb not null,
  result          jsonb not null,
  engine_version  text,
  requested_by    uuid references auth.users (id) on delete set null,
  created_at      timestamptz not null default now()
);
create index estimates_farm_idx on public.estimates (farm_id, year);

create table public.vintages (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references public.organizations (id) on delete cascade,
  project_id    uuid not null references public.projects (id) on delete cascade,
  year          int not null,
  gross_t       numeric(14, 4) not null default 0,
  net_t         numeric(14, 4) not null default 0,
  issuable      int not null default 0 check (issuable >= 0),
  status        text not null default 'draft'
                check (status in ('draft', 'submitted', 'approved', 'on_hold', 'issued')),
  derivation    jsonb not null default '{}'::jsonb,
  submitted_by  uuid references auth.users (id) on delete set null,
  approved_by   uuid references auth.users (id) on delete set null,
  serial_start  bigint,
  serial_end    bigint,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (project_id, year)
);
create index vintages_org_idx on public.vintages (org_id);

create table public.vintage_events (
  id          bigint generated always as identity primary key,
  org_id      uuid not null references public.organizations (id) on delete cascade,
  vintage_id  uuid not null references public.vintages (id) on delete cascade,
  from_status text,
  to_status   text not null,
  note        text,
  actor       uuid references auth.users (id) on delete set null,
  at          timestamptz not null default now()
);
create index vintage_events_vintage_idx on public.vintage_events (vintage_id);

create table public.payments (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references public.organizations (id) on delete cascade,
  vintage_id  uuid not null references public.vintages (id) on delete cascade,
  farmer_id   uuid not null references public.farmers (id) on delete restrict,
  credits     numeric(14, 4) not null check (credits >= 0),
  amount      numeric(14, 2) not null check (amount >= 0),
  currency    text not null default 'USD',
  status      text not null default 'pending'
              check (status in ('pending', 'approved', 'paid', 'failed')),
  due_on      date,
  paid_on     date,
  reference   text,
  created_at  timestamptz not null default now(),
  unique (vintage_id, farmer_id)
);
create index payments_org_idx on public.payments (org_id);

create table public.integrations (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references public.organizations (id) on delete cascade,
  provider      text not null,
  enabled       boolean not null default true,
  config        jsonb not null default '{}'::jsonb,   -- never secrets; those live in env
  last_sync_at  timestamptz,
  last_status   text,
  created_at    timestamptz not null default now(),
  unique (org_id, provider)
);

-- Append-only record of who changed what. Written by trigger, readable by
-- members, writable by nobody through the API.
create table public.audit_events (
  id          bigint generated always as identity primary key,
  org_id      uuid not null,
  actor       uuid,
  action      text not null,
  entity      text not null,
  entity_id   text,
  detail      jsonb,
  at          timestamptz not null default now()
);
create index audit_events_org_idx on public.audit_events (org_id, at desc);

-- ---------------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------------

create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger farms_touch before update on public.farms
  for each row execute function public.touch_updated_at();
create trigger vintages_touch before update on public.vintages
  for each row execute function public.touch_updated_at();

create or replace function public.audit()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  row_data jsonb := to_jsonb(coalesce(new, old));
begin
  insert into public.audit_events (org_id, actor, action, entity, entity_id, detail)
  values ((row_data->>'org_id')::uuid, auth.uid(), lower(tg_op), tg_table_name,
          row_data->>'id',
          case when tg_op = 'UPDATE' then
            (select jsonb_object_agg(k, v) from jsonb_each(to_jsonb(new)) as n(k, v)
             where to_jsonb(old)->k is distinct from v)
          else null end);
  return coalesce(new, old);
end;
$$;

do $$
declare t text;
begin
  foreach t in array array['projects', 'farmers', 'farms', 'practice_records',
                           'soil_samples', 'vintages', 'payments', 'memberships',
                           'integrations']
  loop
    execute format('create trigger %I_audit after insert or update or delete on public.%I
                    for each row execute function public.audit()', t, t);
  end loop;
end;
$$;

-- A farm's farmer and project must belong to the farm's own organisation;
-- foreign keys alone would let one org point at another org's farmer.
create or replace function public.check_same_org()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if tg_table_name = 'farms' then
    if new.farmer_id is not null and not exists (
        select 1 from public.farmers where id = new.farmer_id and org_id = new.org_id) then
      raise exception 'farmer belongs to another organisation';
    end if;
    if new.project_id is not null and not exists (
        select 1 from public.projects where id = new.project_id and org_id = new.org_id) then
      raise exception 'project belongs to another organisation';
    end if;
  elsif tg_table_name in ('practice_records', 'soil_samples', 'estimates') then
    if not exists (select 1 from public.farms where id = new.farm_id and org_id = new.org_id) then
      raise exception 'farm belongs to another organisation';
    end if;
  elsif tg_table_name = 'vintages' then
    if not exists (select 1 from public.projects where id = new.project_id and org_id = new.org_id) then
      raise exception 'project belongs to another organisation';
    end if;
  elsif tg_table_name = 'payments' then
    if not exists (select 1 from public.vintages where id = new.vintage_id and org_id = new.org_id)
       or not exists (select 1 from public.farmers where id = new.farmer_id and org_id = new.org_id) then
      raise exception 'vintage or farmer belongs to another organisation';
    end if;
  end if;
  return new;
end;
$$;

do $$
declare t text;
begin
  foreach t in array array['farms', 'practice_records', 'soil_samples', 'estimates',
                           'vintages', 'payments']
  loop
    execute format('create trigger %I_same_org before insert or update on public.%I
                    for each row execute function public.check_same_org()', t, t);
  end loop;
end;
$$;

-- New auth user -> profile row.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, full_name, phone)
  values (new.id, new.raw_user_meta_data->>'full_name', new.phone)
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- RPCs: the operations that must be atomic or need rules RLS cannot express
-- ---------------------------------------------------------------------------

create or replace function public.create_organization(org_name text, org_kind text default 'developer',
                                                      org_country text default null)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  new_id uuid;
begin
  if auth.uid() is null then
    raise exception 'sign in first';
  end if;
  insert into public.organizations (name, kind, country, created_by)
  values (org_name, org_kind, org_country, auth.uid())
  returning id into new_id;
  insert into public.memberships (org_id, user_id, role) values (new_id, auth.uid(), 'owner');
  return new_id;
end;
$$;

create or replace function public.accept_invitation(invite_token text)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  inv public.invitations;
  user_email text;
begin
  select email into user_email from auth.users where id = auth.uid();
  select * into inv from public.invitations
   where token = invite_token and accepted_at is null and expires_at > now()
   for update;
  if inv.id is null then
    raise exception 'invitation is invalid or has expired';
  end if;
  if lower(inv.email) <> lower(coalesce(user_email, '')) then
    raise exception 'this invitation was sent to a different email address';
  end if;
  insert into public.memberships (org_id, user_id, role)
  values (inv.org_id, auth.uid(), inv.role)
  on conflict (org_id, user_id) do update set role = excluded.role;
  update public.invitations set accepted_at = now() where id = inv.id;
  return inv.org_id;
end;
$$;

-- Vintage review. The allowed moves, and who may make them:
--   draft      -> submitted  analyst, admin, owner
--   submitted  -> approved   reviewer, admin, owner -- never the submitter
--   submitted  -> on_hold    reviewer, admin, owner
--   on_hold    -> submitted  analyst, admin, owner
--   approved   -> issued     admin, owner (allocates serials)
create or replace function public.transition_vintage(vintage uuid, to_state text, review_note text default null)
returns public.vintages language plpgsql security definer set search_path = public as $$
declare
  v public.vintages;
  next_serial bigint;
begin
  select * into v from public.vintages where id = vintage for update;
  if v.id is null or not public.is_member(v.org_id) then
    raise exception 'vintage not found';
  end if;

  if (v.status, to_state) in (('draft', 'submitted'), ('on_hold', 'submitted')) then
    if not public.can_manage(v.org_id) then raise exception 'not allowed to submit'; end if;
    update public.vintages set status = to_state, submitted_by = auth.uid() where id = v.id;
  elsif (v.status, to_state) in (('submitted', 'approved'), ('submitted', 'on_hold')) then
    if not public.has_role(v.org_id, array['owner', 'admin', 'reviewer']) then
      raise exception 'not allowed to review';
    end if;
    if to_state = 'approved' and v.submitted_by = auth.uid() then
      raise exception 'a vintage needs a second person to approve it';
    end if;
    if to_state = 'on_hold' and coalesce(trim(review_note), '') = '' then
      raise exception 'say why the vintage is on hold';
    end if;
    update public.vintages
       set status = to_state,
           approved_by = case when to_state = 'approved' then auth.uid() else null end
     where id = v.id;
  elsif (v.status, to_state) = ('approved', 'issued') then
    if not public.can_administer(v.org_id) then raise exception 'not allowed to issue'; end if;
    if v.issuable <= 0 then raise exception 'nothing to issue: fewer than one whole credit'; end if;
    perform pg_advisory_xact_lock(hashtext(v.org_id::text));
    select coalesce(max(serial_end), 0) + 1 into next_serial
      from public.vintages where org_id = v.org_id;
    update public.vintages
       set status = 'issued', serial_start = next_serial,
           serial_end = next_serial + v.issuable - 1
     where id = v.id;
  else
    raise exception 'cannot move a vintage from % to %', v.status, to_state;
  end if;

  insert into public.vintage_events (org_id, vintage_id, from_status, to_status, note, actor)
  values (v.org_id, v.id, v.status, to_state, review_note, auth.uid());

  select * into v from public.vintages where id = vintage;
  return v;
end;
$$;

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------

alter table public.profiles          enable row level security;
alter table public.organizations     enable row level security;
alter table public.memberships       enable row level security;
alter table public.invitations       enable row level security;
alter table public.projects          enable row level security;
alter table public.farmers           enable row level security;
alter table public.farms             enable row level security;
alter table public.practice_records  enable row level security;
alter table public.soil_samples      enable row level security;
alter table public.imports           enable row level security;
alter table public.estimates         enable row level security;
alter table public.vintages          enable row level security;
alter table public.vintage_events    enable row level security;
alter table public.payments          enable row level security;
alter table public.integrations      enable row level security;
alter table public.audit_events      enable row level security;

-- Profiles: yourself, and people you share an organisation with.
create policy profiles_read on public.profiles for select using (
  id = auth.uid() or exists (
    select 1 from public.memberships mine
    join public.memberships theirs on theirs.org_id = mine.org_id
    where mine.user_id = auth.uid() and theirs.user_id = profiles.id));
create policy profiles_write on public.profiles for update using (id = auth.uid())
  with check (id = auth.uid());

-- Organisations: created only through create_organization().
create policy orgs_read on public.organizations for select using (public.is_member(id));
create policy orgs_update on public.organizations for update
  using (public.can_administer(id)) with check (public.can_administer(id));

-- Memberships: admins manage; nobody can grant 'owner' except an owner, and
-- an admin cannot touch an owner's row.
create policy members_read on public.memberships for select using (public.is_member(org_id));
create policy members_insert on public.memberships for insert with check (
  public.can_administer(org_id)
  and (role <> 'owner' or public.has_role(org_id, array['owner'])));
create policy members_update on public.memberships for update
  using (public.can_administer(org_id)
         and (role <> 'owner' or public.has_role(org_id, array['owner'])))
  with check (role <> 'owner' or public.has_role(org_id, array['owner']));
create policy members_delete on public.memberships for delete using (
  (public.can_administer(org_id) and (role <> 'owner' or public.has_role(org_id, array['owner'])))
  or (user_id = auth.uid() and role <> 'owner'));

create policy invites_read on public.invitations for select using (public.can_administer(org_id));
create policy invites_write on public.invitations for insert with check (public.can_administer(org_id));
create policy invites_delete on public.invitations for delete using (public.can_administer(org_id));

-- Field data: any member reads; enrolling roles write.
do $$
declare t text;
begin
  foreach t in array array['farmers', 'farms', 'practice_records', 'soil_samples']
  loop
    execute format('create policy %I_read on public.%I for select using (public.is_member(org_id))', t, t);
    execute format('create policy %I_insert on public.%I for insert with check (public.can_enrol(org_id))', t, t);
    execute format('create policy %I_update on public.%I for update using (public.can_enrol(org_id)) with check (public.can_enrol(org_id))', t, t);
    execute format('create policy %I_delete on public.%I for delete using (public.can_manage(org_id))', t, t);
  end loop;
end;
$$;

create policy imports_read on public.imports for select using (public.is_member(org_id));
create policy imports_insert on public.imports for insert with check (public.can_enrol(org_id));

create policy projects_read on public.projects for select using (public.is_member(org_id));
create policy projects_insert on public.projects for insert with check (public.can_manage(org_id));
create policy projects_update on public.projects for update
  using (public.can_manage(org_id)) with check (public.can_manage(org_id));
create policy projects_delete on public.projects for delete using (public.can_administer(org_id));

create policy estimates_read on public.estimates for select using (public.is_member(org_id));
create policy estimates_insert on public.estimates for insert with check (public.can_enrol(org_id));

-- Vintages: analysts create and edit drafts; every status change goes
-- through transition_vintage(), so plain updates may not touch status.
create policy vintages_read on public.vintages for select using (public.is_member(org_id));
create policy vintages_insert on public.vintages for insert
  with check (public.can_manage(org_id) and status = 'draft');
create policy vintages_update on public.vintages for update
  using (public.can_manage(org_id) and status = 'draft')
  with check (public.can_manage(org_id) and status = 'draft');
create policy vintages_delete on public.vintages for delete
  using (public.can_administer(org_id) and status = 'draft');

create policy vintage_events_read on public.vintage_events for select using (public.is_member(org_id));

-- Payments are raised and settled by admins only.
create policy payments_read on public.payments for select using (public.is_member(org_id));
create policy payments_insert on public.payments for insert with check (public.can_administer(org_id));
create policy payments_update on public.payments for update
  using (public.can_administer(org_id)) with check (public.can_administer(org_id));

create policy integrations_read on public.integrations for select using (public.is_member(org_id));
create policy integrations_write on public.integrations for all
  using (public.can_administer(org_id)) with check (public.can_administer(org_id));

create policy audit_read on public.audit_events for select using (public.is_member(org_id));

-- ---------------------------------------------------------------------------
-- Grants. Supabase grants table access to anon/authenticated by default; the
-- app never needs anon access to customer data, so take it away explicitly.
-- ---------------------------------------------------------------------------

revoke all on all tables in schema public from anon;
revoke execute on all functions in schema public from anon, public;
grant execute on function public.create_organization(text, text, text) to authenticated;
grant execute on function public.accept_invitation(text) to authenticated;
grant execute on function public.transition_vintage(uuid, text, text) to authenticated;
grant execute on function public.is_member(uuid) to authenticated;
grant execute on function public.has_role(uuid, text[]) to authenticated;
grant execute on function public.can_enrol(uuid) to authenticated;
grant execute on function public.can_manage(uuid) to authenticated;
grant execute on function public.can_administer(uuid) to authenticated;
