-- Who may count an issued credit, and the record of it being used up.
--
-- Mirrors carbonstack.article6. A host country's letter of authorisation is
-- a promise; the corresponding adjustment is the promise kept. Only credits
-- with an adjustment behind them may be retired as an offset against a
-- buyer's own target (or for CORSIA, if that is what was authorised).
-- Everything else may only be retired as a contribution: the buyer financed
-- the reduction, and the host country still counts it.
--
-- Retirement takes serials from an issued vintage in order, so every credit
-- has exactly one fate, and anyone can check it at /verify without signing
-- in. The public functions return registry facts only, never farmer data.

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.authorisations (
  id                    uuid primary key default gen_random_uuid(),
  org_id                uuid not null references public.organizations (id) on delete cascade,
  project_id            uuid not null references public.projects (id) on delete cascade,
  authority             text not null check (length(trim(authority)) > 1),
  reference             text not null check (length(trim(reference)) > 1),
  issued_on             date not null,
  authorised_use        text not null
                        check (authorised_use in ('other_party_ndc', 'corsia',
                                                  'other_international_mitigation_purposes')),
  authorised_volume_t   numeric(14, 4) not null check (authorised_volume_t > 0),
  adjustment_committed  boolean not null,
  first_vintage         int not null,
  last_vintage          int not null,
  valid_until           date,
  revoked_on            date,
  created_by            uuid references auth.users (id) on delete set null,
  created_at            timestamptz not null default now(),
  check (last_vintage >= first_vintage)
);
create index authorisations_project_idx on public.authorisations (project_id);

create table public.adjustments (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references public.organizations (id) on delete cascade,
  authorisation_id  uuid not null references public.authorisations (id) on delete cascade,
  vintage_year      int not null,
  volume_t          numeric(14, 4) not null check (volume_t > 0),
  reported_on       date not null,
  reference         text not null check (length(trim(reference)) > 1),
  created_by        uuid references auth.users (id) on delete set null,
  created_at        timestamptz not null default now()
);
create index adjustments_authorisation_idx on public.adjustments (authorisation_id);

create table public.retirements (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references public.organizations (id) on delete cascade,
  vintage_id    uuid not null references public.vintages (id) on delete restrict,
  serial_start  bigint not null,
  serial_end    bigint not null,
  quantity      int generated always as ((serial_end - serial_start + 1)::int) stored,
  beneficiary   text not null check (length(trim(beneficiary)) > 1),
  purpose       text not null check (purpose in ('contribution', 'offset', 'corsia')),
  claim         text not null,
  retired_by    uuid references auth.users (id) on delete set null,
  retired_at    timestamptz not null default now(),
  check (serial_end >= serial_start)
);
create index retirements_vintage_idx on public.retirements (vintage_id);

-- ---------------------------------------------------------------------------
-- Same-organisation guards and audit, as for the core tables
-- ---------------------------------------------------------------------------

create or replace function public.check_claims_same_org()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if tg_table_name = 'authorisations' then
    if not exists (select 1 from public.projects where id = new.project_id and org_id = new.org_id) then
      raise exception 'project belongs to another organisation';
    end if;
  elsif tg_table_name = 'adjustments' then
    if not exists (select 1 from public.authorisations where id = new.authorisation_id and org_id = new.org_id) then
      raise exception 'authorisation belongs to another organisation';
    end if;
  end if;
  return new;
end;
$$;

create trigger authorisations_same_org before insert or update on public.authorisations
  for each row execute function public.check_claims_same_org();
create trigger adjustments_same_org before insert or update on public.adjustments
  for each row execute function public.check_claims_same_org();

create trigger authorisations_audit after insert or update or delete on public.authorisations
  for each row execute function public.audit();
create trigger adjustments_audit after insert or update or delete on public.adjustments
  for each row execute function public.audit();
create trigger retirements_audit after insert or update or delete on public.retirements
  for each row execute function public.audit();

-- ---------------------------------------------------------------------------
-- What a vintage permits (carbonstack.article6.classify, in SQL)
-- ---------------------------------------------------------------------------

-- SECURITY INVOKER on purpose: called directly it reads authorisations and
-- retirements under the caller's own row-level security, so a hand-built
-- vintage row cannot be used to peek at another organisation's letters. The
-- public lookups below call it from inside their own definer context.
create or replace function public.claim_basis(v public.vintages)
returns jsonb language plpgsql stable security invoker set search_path = public as $$
declare
  auth public.authorisations;
  adjusted numeric := 0;
  offsettable int := 0;
  retired_offset int := 0;
  basis text := 'unadjusted_voluntary';
  reasons text[] := array[]::text[];
begin
  -- The most recent live authorisation covering this vintage.
  select * into auth from public.authorisations a
   where a.project_id = v.project_id
     and v.year between a.first_vintage and a.last_vintage
     and (a.revoked_on is null or a.revoked_on > current_date)
     and (a.valid_until is null or a.valid_until >= current_date)
   order by a.issued_on desc
   limit 1;

  if auth.id is null then
    reasons := array_append(reasons, 'no host-country authorisation on record');
  elsif not auth.adjustment_committed then
    reasons := array_append(reasons, 'the authorisation does not commit to a corresponding adjustment');
  else
    basis := 'authorised_itmo';
    select coalesce(sum(volume_t), 0) into adjusted from public.adjustments
     where authorisation_id = auth.id and vintage_year = v.year;
    if adjusted = 0 then
      reasons := array_append(reasons, 'authorised, but no corresponding adjustment has been applied for this vintage yet');
    end if;
  end if;

  -- Whole credits only, and never more than were issued.
  offsettable := least(floor(adjusted)::int, v.issuable);
  select coalesce(sum(quantity), 0) into retired_offset from public.retirements
   where vintage_id = v.id and purpose in ('offset', 'corsia');

  return jsonb_build_object(
    'basis', basis,
    'authorisation', case when auth.id is null then null else jsonb_build_object(
      'reference', auth.reference, 'authority', auth.authority,
      'authorised_use', auth.authorised_use,
      'adjustment_committed', auth.adjustment_committed) end,
    'adjusted_t', adjusted,
    'offsettable_credits', offsettable,
    'offset_remaining', greatest(offsettable - retired_offset, 0),
    'corsia_eligible', basis = 'authorised_itmo' and auth.authorised_use = 'corsia' and offsettable > 0,
    'reasons', to_jsonb(reasons));
end;
$$;

/** Every vintage's claim basis for one organisation, under the caller's RLS. */
create or replace function public.vintage_claims(org uuid)
returns table (vintage_id uuid, basis jsonb) language sql stable security invoker set search_path = public as $$
  select v.id, public.claim_basis(v) from public.vintages v where v.org_id = org;
$$;

-- What a retirement lets its beneficiary say. Stored on the retirement, so
-- the certificate keeps the words it was issued with.
create or replace function public.claim_text(purpose text, beneficiary text, host text)
returns text language sql immutable as $$
  select case purpose
    when 'contribution' then
      format('%s financed these emission reductions. They remain counted by %s toward its own climate '
             'target and may not be counted against %s''s own emissions target.', beneficiary, host, beneficiary)
    when 'offset' then
      format('Retired on behalf of %s against its own emissions target. %s has applied a corresponding '
             'adjustment, so these tonnes are not also counted by the host country.', beneficiary, host)
    else
      format('Retired on behalf of %s for use under CORSIA. %s authorised these tonnes for CORSIA and has '
             'applied a corresponding adjustment.', beneficiary, host)
  end;
$$;

-- ---------------------------------------------------------------------------
-- Retirement
-- ---------------------------------------------------------------------------

create or replace function public.retire_credits(vintage uuid, credits int, beneficiary_name text,
                                                 retire_purpose text)
returns public.retirements language plpgsql security definer set search_path = public as $$
declare
  v public.vintages;
  p public.projects;
  basis jsonb;
  retired int;
  r public.retirements;
begin
  select * into v from public.vintages where id = vintage for update;
  if v.id is null or not public.is_member(v.org_id) then
    raise exception 'vintage not found';
  end if;
  if not public.can_administer(v.org_id) then
    raise exception 'only owners and admins retire credits';
  end if;
  if v.status <> 'issued' then
    raise exception 'only issued credits can be retired';
  end if;
  if credits is null or credits < 1 then
    raise exception 'retire at least one whole credit';
  end if;
  if retire_purpose not in ('contribution', 'offset', 'corsia') then
    raise exception 'unknown retirement purpose';
  end if;
  if coalesce(trim(beneficiary_name), '') = '' then
    raise exception 'name the beneficiary';
  end if;

  select coalesce(sum(quantity), 0) into retired from public.retirements where vintage_id = v.id;
  if retired + credits > v.issuable then
    raise exception 'only % credits of this vintage are left to retire', v.issuable - retired;
  end if;

  basis := public.claim_basis(v);
  if retire_purpose in ('offset', 'corsia') then
    if (basis->>'offset_remaining')::int < credits then
      raise exception 'only % credits of this vintage have a corresponding adjustment behind them; retire the rest as a contribution',
        (basis->>'offset_remaining')::int;
    end if;
    if retire_purpose = 'corsia' and not (basis->>'corsia_eligible')::boolean then
      raise exception 'this vintage is not authorised for CORSIA';
    end if;
  end if;

  select * into p from public.projects where id = v.project_id;
  insert into public.retirements (org_id, vintage_id, serial_start, serial_end, beneficiary, purpose,
                                  claim, retired_by)
  values (v.org_id, v.id, v.serial_start + retired, v.serial_start + retired + credits - 1,
          trim(beneficiary_name), retire_purpose,
          public.claim_text(retire_purpose, trim(beneficiary_name), coalesce(p.country, 'the host country')),
          auth.uid())
  returning * into r;
  return r;
end;
$$;

-- ---------------------------------------------------------------------------
-- Public verification. Registry facts only: no farmer, farm or payment data.
-- ---------------------------------------------------------------------------

/** The short code that prefixes every credit serial: the first eight hex
    digits of the organisation id, upper-cased. */
create or replace function public.org_code(org uuid)
returns text language sql immutable as $$
  select upper(substr(replace(org::text, '-', ''), 1, 8));
$$;

create or replace function public.public_vintage(v public.vintages)
returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'organisation', o.name,
    'org_code', public.org_code(o.id),
    'project', p.name,
    'methodology', p.methodology,
    'registry', p.registry,
    'country', p.country,
    'region', p.region,
    'vintage_year', v.year,
    'net_t', v.net_t,
    'serial_start', v.serial_start,
    'serial_end', v.serial_end,
    'issued_at', (select max(e.at) from public.vintage_events e
                  where e.vintage_id = v.id and e.to_status = 'issued'),
    'claim_basis', public.claim_basis(v))
  from public.organizations o, public.projects p
  where o.id = v.org_id and p.id = v.project_id;
$$;

/** Look up one credit by its code, e.g. 3F2A9C1B-2025-17. */
create or replace function public.verify_credit(code text)
returns jsonb language plpgsql stable security definer set search_path = public as $$
declare
  m text[];
  v public.vintages;
  matches int;
  r public.retirements;
begin
  m := regexp_match(upper(trim(code)), '^([0-9A-F]{8})-(\d{4})-0*(\d{1,12})$');
  if m is null then
    return jsonb_build_object('found', false, 'reason', 'codes look like ABCD1234-2025-17');
  end if;
  select count(*) into matches from public.vintages vv
   where public.org_code(vv.org_id) = m[1] and vv.year = m[2]::int and vv.status = 'issued'
     and m[3]::bigint between vv.serial_start and vv.serial_end;
  if matches <> 1 then
    return jsonb_build_object('found', false, 'reason', 'no issued credit has that code');
  end if;
  select vv.* into v from public.vintages vv
   where public.org_code(vv.org_id) = m[1] and vv.year = m[2]::int and vv.status = 'issued'
     and m[3]::bigint between vv.serial_start and vv.serial_end;
  select * into r from public.retirements
   where vintage_id = v.id and m[3]::bigint between serial_start and serial_end;
  return jsonb_build_object(
    'found', true,
    'serial', m[3]::bigint,
    'code', m[1] || '-' || m[2] || '-' || m[3],
    'vintage', public.public_vintage(v),
    'retirement', case when r.id is null then null else jsonb_build_object(
      'id', r.id, 'beneficiary', r.beneficiary, 'purpose', r.purpose, 'claim', r.claim,
      'retired_at', r.retired_at, 'serial_start', r.serial_start, 'serial_end', r.serial_end,
      'quantity', r.quantity) end);
end;
$$;

/** A retirement certificate, by its id. */
create or replace function public.retirement_certificate(retirement uuid)
returns jsonb language sql stable security definer set search_path = public as $$
  select case when r.id is null then jsonb_build_object('found', false) else jsonb_build_object(
    'found', true,
    'id', r.id, 'beneficiary', r.beneficiary, 'purpose', r.purpose, 'claim', r.claim,
    'retired_at', r.retired_at, 'serial_start', r.serial_start, 'serial_end', r.serial_end,
    'quantity', r.quantity,
    'vintage', public.public_vintage(v)) end
  from (select 1) one
  left join public.retirements r on r.id = retirement
  left join public.vintages v on v.id = r.vintage_id;
$$;

-- ---------------------------------------------------------------------------
-- Row-level security and grants
-- ---------------------------------------------------------------------------

alter table public.authorisations enable row level security;
alter table public.adjustments    enable row level security;
alter table public.retirements    enable row level security;

create policy authorisations_read on public.authorisations for select using (public.is_member(org_id));
create policy authorisations_write on public.authorisations for insert with check (public.can_administer(org_id));
create policy authorisations_update on public.authorisations for update
  using (public.can_administer(org_id)) with check (public.can_administer(org_id));

create policy adjustments_read on public.adjustments for select using (public.is_member(org_id));
create policy adjustments_write on public.adjustments for insert with check (public.can_administer(org_id));

-- Retirements are written only by retire_credits(), and never changed.
create policy retirements_read on public.retirements for select using (public.is_member(org_id));

revoke all on public.authorisations, public.adjustments, public.retirements from anon;
revoke execute on function public.check_claims_same_org(), public.claim_basis(public.vintages),
  public.public_vintage(public.vintages), public.retire_credits(uuid, int, text, text),
  public.verify_credit(text), public.retirement_certificate(uuid), public.org_code(uuid),
  public.claim_text(text, text, text), public.vintage_claims(uuid)
  from anon, public;
grant execute on function public.claim_basis(public.vintages) to authenticated;
grant execute on function public.vintage_claims(uuid) to authenticated;
grant execute on function public.retire_credits(uuid, int, text, text) to authenticated;
grant execute on function public.org_code(uuid) to authenticated;
-- The two lookups anyone may make, signed in or not.
grant execute on function public.verify_credit(text) to anon, authenticated;
grant execute on function public.retirement_certificate(uuid) to anon, authenticated;
