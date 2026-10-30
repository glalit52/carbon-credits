-- Evidence files: consent forms, land records, practice photos, lab reports.
--
-- Objects live under '<org_id>/...' so the first path segment says whose they
-- are, and the policies below read it from there. Private bucket: files are
-- served through short-lived signed URLs, never public links.

insert into storage.buckets (id, name, public, file_size_limit)
values ('evidence', 'evidence', false, 20971520)
on conflict (id) do nothing;

create policy evidence_read on storage.objects for select to authenticated using (
  bucket_id = 'evidence'
  and public.is_member(((storage.foldername(name))[1])::uuid));

create policy evidence_insert on storage.objects for insert to authenticated with check (
  bucket_id = 'evidence'
  and public.can_enrol(((storage.foldername(name))[1])::uuid));

create policy evidence_delete on storage.objects for delete to authenticated using (
  bucket_id = 'evidence'
  and public.can_manage(((storage.foldername(name))[1])::uuid));
