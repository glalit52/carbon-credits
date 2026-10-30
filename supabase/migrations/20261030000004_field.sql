-- Monitoring, registry references, farmer language and farmer statements.
--
-- * Logger uploads: a water-level logger file per farm, cleaned by the engine
--   and kept with its summary, so the radar's track record on this project
--   is measured rather than asserted.
-- * Registry references: the id the registry gave an issued vintage, which
--   is what reconciliation matches on when serial formats differ.
-- * A farmer's language, for statements and the field app.
-- * Statement links: a farmer's own statement, readable without an account
--   through an unguessable link that expires and can be revoked.

-- ---------------------------------------------------------------------------
-- Farmer language
-- ---------------------------------------------------------------------------

alter table public.farmers
  add column language text not null default 'en'
  check (language in ('en', 'hi', 'ta', 'sw'));

-- ---------------------------------------------------------------------------
-- Logger uploads
-- ---------------------------------------------------------------------------

create table public.sensor_uploads (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references public.organizations (id) on delete cascade,
  farm_id      uuid not null references public.farms (id) on delete cascade,
  file_name    text not null,
  file_path    text,                     -- in the evidence bucket, under <org_id>/
  readings     int not null check (readings >= 0),
  first_day    date,
  last_day     date,
  summary      jsonb not null,           -- the engine's cleaned record and validation
  uploaded_by  uuid references auth.users (id) on delete set null,
  created_at   timestamptz not null default now()
);
create index sensor_uploads_farm_idx on public.sensor_uploads (farm_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Registry references on issued vintages
-- ---------------------------------------------------------------------------

alter table public.vintages
  add column registry_ref text,
  add column registry_ref_at timestamptz;

/** Record the registry's id for an issued vintage. Admins only, issued only. */
create or replace function public.set_registry_reference(vintage uuid, ref text)
returns void language plpgsql security definer set search_path = public as $$
declare
  v public.vintages;
begin
  select * into v from public.vintages where id = vintage for update;
  if v.id is null or not public.is_member(v.org_id) then
    raise exception 'vintage not found';
  end if;
  if not public.can_administer(v.org_id) then
    raise exception 'only owners and admins record registry references';
  end if;
  if v.status <> 'issued' then
    raise exception 'only an issued vintage has a registry reference';
  end if;
  if ref is null or length(trim(ref)) = 0 or length(ref) > 200 then
    raise exception 'give the reference the registry shows, up to 200 characters';
  end if;
  update public.vintages set registry_ref = trim(ref), registry_ref_at = now() where id = vintage;
end;
$$;

-- ---------------------------------------------------------------------------
-- Statement links
-- ---------------------------------------------------------------------------

create table public.statement_links (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references public.organizations (id) on delete cascade,
  farmer_id   uuid not null references public.farmers (id) on delete cascade,
  -- 256 bits from two v4 UUIDs (244 random bits); never derived from ids.
  token       text not null unique default
              replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', ''),
  language    text not null default 'en' check (language in ('en', 'hi', 'ta', 'sw')),
  expires_at  timestamptz not null default now() + interval '90 days',
  revoked_at  timestamptz,
  created_by  uuid references auth.users (id) on delete set null,
  created_at  timestamptz not null default now(),
  check (expires_at <= created_at + interval '366 days')
);
create index statement_links_farmer_idx on public.statement_links (farmer_id);

-- Same-org checks for the two new child tables.
create or replace function public.check_field_same_org()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if tg_table_name = 'sensor_uploads' then
    if not exists (select 1 from public.farms where id = new.farm_id and org_id = new.org_id) then
      raise exception 'farm belongs to another organisation';
    end if;
  elsif tg_table_name = 'statement_links' then
    if not exists (select 1 from public.farmers where id = new.farmer_id and org_id = new.org_id) then
      raise exception 'farmer belongs to another organisation';
    end if;
  end if;
  return new;
end;
$$;

create trigger sensor_uploads_same_org before insert or update on public.sensor_uploads
  for each row execute function public.check_field_same_org();
create trigger statement_links_same_org before insert or update on public.statement_links
  for each row execute function public.check_field_same_org();
create trigger sensor_uploads_audit after insert or update or delete on public.sensor_uploads
  for each row execute function public.audit();
create trigger statement_links_audit after insert or update or delete on public.statement_links
  for each row execute function public.audit();

/**
 * A farmer's statement, by link token: their farms, what each vintage paid
 * them, and what is still missing from their paperwork. Nothing about any
 * other farmer, and nothing at all once the link has expired or been revoked.
 */
create or replace function public.farmer_statement(link_token text)
returns jsonb language plpgsql stable security definer set search_path = public as $$
declare
  l public.statement_links;
  f public.farmers;
begin
  if link_token is null or link_token !~ '^[0-9a-f]{64}$' then
    return jsonb_build_object('found', false);
  end if;
  select * into l from public.statement_links where token = link_token;
  if l.id is null or l.revoked_at is not null or l.expires_at < now() then
    return jsonb_build_object('found', false);
  end if;
  select * into f from public.farmers where id = l.farmer_id;
  return jsonb_build_object(
    'found', true,
    'language', l.language,
    'expires_at', l.expires_at,
    'generated_at', now(),
    'organisation', (select name from public.organizations where id = l.org_id),
    'farmer', jsonb_build_object(
      'name', f.name, 'village', f.village, 'district', f.district, 'state', f.state,
      'country', f.country, 'external_ref', f.external_ref,
      'consent', f.consent_on is not null,
      'carbon_rights', f.carbon_rights_ref is not null,
      'payout_method', f.payout_method),
    'farms', coalesce((
      select jsonb_agg(jsonb_build_object(
        'name', fm.name, 'area_ha', fm.area_ha, 'pathway', p.pathway, 'crop', fm.crop, 'status', fm.status,
        'practice', fm.practice, 'tenure_document', fm.tenure_reference is not null,
        'project', p.name,
        'latest_year', est.year, 'latest_net_t', est.net_t)
        order by fm.name)
      from public.farms fm left join public.projects p on p.id = fm.project_id
      -- One run stores a row per year; the statement shows the latest run's
      -- latest year.
      left join lateral (select e.year, e.net_t from public.estimates e where e.farm_id = fm.id
                         order by e.created_at desc, e.year desc limit 1) est on true
      where fm.farmer_id = f.id and fm.status <> 'withdrawn'), '[]'::jsonb),
    'payments', coalesce((
      select jsonb_agg(jsonb_build_object(
        'vintage_year', v.year, 'project', p.name, 'credits', pm.credits,
        'amount', pm.amount, 'currency', pm.currency, 'status', pm.status,
        'due_on', pm.due_on, 'paid_on', pm.paid_on,
        -- The last four characters are enough to find it on a bank statement.
        'reference_tail', case when pm.reference is null then null
                               else right(pm.reference, 4) end)
        order by v.year desc, p.name)
      from public.payments pm
      join public.vintages v on v.id = pm.vintage_id
      join public.projects p on p.id = v.project_id
      where pm.farmer_id = f.id), '[]'::jsonb));
end;
$$;

-- ---------------------------------------------------------------------------
-- Access
-- ---------------------------------------------------------------------------

alter table public.sensor_uploads  enable row level security;
alter table public.statement_links enable row level security;

create policy sensor_uploads_read on public.sensor_uploads for select using (public.is_member(org_id));
create policy sensor_uploads_insert on public.sensor_uploads for insert
  with check (public.can_enrol(org_id) and uploaded_by = auth.uid());
create policy sensor_uploads_delete on public.sensor_uploads for delete using (public.can_manage(org_id));

-- Sharing a farmer's statement is an enrolling role's job: the field agent
-- who sits with the farmer is usually the one who sends it.
create policy statement_links_read on public.statement_links for select using (public.is_member(org_id));
create policy statement_links_insert on public.statement_links for insert
  with check (public.can_enrol(org_id) and created_by = auth.uid() and revoked_at is null);
-- Revoking is the only change: the token, farmer and expiry stay as issued.
create policy statement_links_revoke on public.statement_links for update
  using (public.can_enrol(org_id)) with check (public.can_enrol(org_id) and revoked_at is not null);

create or replace function public.statement_links_immutable()
returns trigger language plpgsql as $$
begin
  if new.token <> old.token or new.farmer_id <> old.farmer_id or new.org_id <> old.org_id
     or new.expires_at <> old.expires_at or new.language <> old.language
     or new.created_at <> old.created_at or old.revoked_at is not null then
    raise exception 'a statement link can only be revoked';
  end if;
  return new;
end;
$$;
create trigger statement_links_only_revoke before update on public.statement_links
  for each row execute function public.statement_links_immutable();

revoke all on public.sensor_uploads, public.statement_links from anon;
revoke execute on function public.set_registry_reference(uuid, text),
  public.farmer_statement(text), public.check_field_same_org(),
  public.statement_links_immutable()
  from anon, public;
grant execute on function public.set_registry_reference(uuid, text) to authenticated;
-- The farmer opens their statement without an account.
grant execute on function public.farmer_statement(text) to anon, authenticated;
