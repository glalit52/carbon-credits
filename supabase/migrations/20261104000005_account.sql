-- Accounts: a person can close their own account from their profile.
--
-- The organisation's records stay. Every created_by / recorded_by column is
-- `on delete set null`, so farms, vintages and payments keep existing with
-- no author, and audit_events keeps the actor's id as it was written.

-- A revoked statement link refused every later update, including the
-- `created_by -> null` that deleting its author performs. Allow exactly that
-- one change; everything else about a link is still fixed once issued.
create or replace function public.statement_links_immutable()
returns trigger language plpgsql as $$
begin
  if new.token <> old.token or new.farmer_id <> old.farmer_id or new.org_id <> old.org_id
     or new.expires_at <> old.expires_at or new.language <> old.language
     or new.created_at <> old.created_at
     or (old.revoked_at is not null and new.revoked_at is distinct from old.revoked_at)
     or (new.created_by is distinct from old.created_by and new.created_by is not null) then
    raise exception 'a statement link can only be revoked';
  end if;
  return new;
end;
$$;

-- Delete the caller's own account. Refused while they are the last owner of
-- an organisation: issued credits and their audit trail must always have
-- someone who can answer for them, so ownership is handed over first.
create or replace function public.delete_own_account()
returns void language plpgsql security definer set search_path = public as $$
declare
  stranded text;
begin
  if auth.uid() is null then
    raise exception 'sign in first';
  end if;
  select string_agg(o.name, ', ' order by o.name) into stranded
    from public.memberships m
    join public.organizations o on o.id = m.org_id
   where m.user_id = auth.uid() and m.role = 'owner'
     and not exists (
       select 1 from public.memberships other
        where other.org_id = m.org_id and other.role = 'owner' and other.user_id <> auth.uid());
  if stranded is not null then
    raise exception 'you are the only owner of %; make someone else an owner first', stranded;
  end if;
  delete from auth.users where id = auth.uid();
end;
$$;

revoke execute on function public.delete_own_account() from anon, public;
grant execute on function public.delete_own_account() to authenticated;
