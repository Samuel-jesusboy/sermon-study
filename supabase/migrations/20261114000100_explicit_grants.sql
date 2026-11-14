-- Explicit table privileges. This project does not auto-grant new tables to the API roles, and the
-- original tables had full anon write access. Signed-in users get normal CRUD (RLS still limits rows);
-- anonymous visitors can only read (RLS limits that to sermons marked public).

revoke all on public.sermons, public.churches, public.study_guides, public.jobs, public.sermon_chunks
  from anon, authenticated;

grant select, insert, update, delete
  on public.sermons, public.churches, public.study_guides, public.jobs, public.sermon_chunks
  to authenticated;

grant select on public.sermons to anon;

grant usage, select on all sequences in schema public to authenticated;

grant all on public.sermons, public.churches, public.study_guides, public.jobs, public.sermon_chunks
  to service_role;
