-- Sermon Study v2: user accounts, per-user data, background jobs, semantic search, public sharing.
-- Applied on top of the original SUPABASE_SCHEMA.sql (tables sermons, churches, study_guides).

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- Ownership columns
-- ---------------------------------------------------------------------------
alter table public.sermons
  add column if not exists user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  add column if not exists church_id uuid references public.churches (id) on delete set null,
  add column if not exists source text not null default 'youtube',
  add column if not exists is_public boolean not null default false,
  add column if not exists duration_seconds integer,
  add column if not exists topics text[] not null default '{}';

alter table public.churches
  add column if not exists user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  add column if not exists auto_import boolean not null default false,
  add column if not exists last_checked_at timestamptz;

alter table public.study_guides
  add column if not exists user_id uuid not null default auth.uid() references auth.users (id) on delete cascade;

create index if not exists sermons_user_created_idx on public.sermons (user_id, created_at desc);
create index if not exists sermons_user_video_idx on public.sermons (user_id, video_id);
create index if not exists sermons_topics_idx on public.sermons using gin (topics);
create index if not exists sermons_church_idx on public.sermons (church_id);
create index if not exists churches_user_idx on public.churches (user_id);
create index if not exists study_guides_user_idx on public.study_guides (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Background jobs (sermon processing runs outside the web request)
-- ---------------------------------------------------------------------------
create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  kind text not null default 'sermon',
  status text not null default 'queued' check (status in ('queued', 'running', 'done', 'failed')),
  step text not null default 'Queued',
  progress integer not null default 0 check (progress between 0 and 100),
  input jsonb not null default '{}',
  sermon_id uuid references public.sermons (id) on delete set null,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists jobs_user_created_idx on public.jobs (user_id, created_at desc);
create index if not exists jobs_sermon_idx on public.jobs (sermon_id);

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists jobs_touch_updated_at on public.jobs;
create trigger jobs_touch_updated_at before update on public.jobs
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Transcript chunks for search (full-text always; vectors when an embedding key is set)
-- ---------------------------------------------------------------------------
create table if not exists public.sermon_chunks (
  id bigint generated always as identity primary key,
  sermon_id uuid not null references public.sermons (id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  chunk_index integer not null,
  start_seconds integer not null default 0,
  content text not null,
  embedding extensions.vector(1536),
  fts tsvector generated always as (to_tsvector('english', content)) stored
);
create index if not exists sermon_chunks_sermon_idx on public.sermon_chunks (sermon_id, chunk_index);
create index if not exists sermon_chunks_user_idx on public.sermon_chunks (user_id);
create index if not exists sermon_chunks_fts_idx on public.sermon_chunks using gin (fts);
create index if not exists sermon_chunks_embedding_idx on public.sermon_chunks
  using hnsw (embedding extensions.vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- Row level security: replace the old "Allow all" policies
-- ---------------------------------------------------------------------------
drop policy if exists "Allow all" on public.sermons;
drop policy if exists "Allow all" on public.churches;
drop policy if exists "Allow all" on public.study_guides;

alter table public.sermons enable row level security;
alter table public.churches enable row level security;
alter table public.study_guides enable row level security;
alter table public.jobs enable row level security;
alter table public.sermon_chunks enable row level security;

-- sermons: owners do everything; anyone may read a sermon its owner chose to share
create policy "sermons_select_own_or_public" on public.sermons
  for select to anon, authenticated
  using (is_public or (select auth.uid()) = user_id);
create policy "sermons_insert_own" on public.sermons
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "sermons_update_own" on public.sermons
  for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "sermons_delete_own" on public.sermons
  for delete to authenticated using ((select auth.uid()) = user_id);

-- churches, study guides, jobs, chunks: owner only
create policy "churches_own" on public.churches
  for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "study_guides_own" on public.study_guides
  for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "jobs_own" on public.jobs
  for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "sermon_chunks_own" on public.sermon_chunks
  for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- Search functions (security invoker, so RLS limits results to the caller's data)
-- ---------------------------------------------------------------------------
create or replace function public.match_sermon_chunks(
  query_embedding extensions.vector(1536),
  match_count integer default 8
)
returns table (sermon_id uuid, chunk_index integer, start_seconds integer, content text, score double precision)
language sql
stable
security invoker
set search_path = ''
as $$
  select c.sermon_id, c.chunk_index, c.start_seconds, c.content,
         1 - (c.embedding operator(extensions.<=>) query_embedding) as score
  from public.sermon_chunks c
  where c.embedding is not null
  order by c.embedding operator(extensions.<=>) query_embedding
  limit least(match_count, 50);
$$;

create or replace function public.search_sermon_chunks(
  query text,
  match_count integer default 8
)
returns table (sermon_id uuid, chunk_index integer, start_seconds integer, content text, score double precision)
language sql
stable
security invoker
set search_path = ''
as $$
  select c.sermon_id, c.chunk_index, c.start_seconds, c.content,
         ts_rank_cd(c.fts, websearch_to_tsquery('english', query))::double precision as score
  from public.sermon_chunks c
  where c.fts @@ websearch_to_tsquery('english', query)
  order by score desc
  limit least(match_count, 50);
$$;

revoke execute on function public.match_sermon_chunks(extensions.vector, integer) from anon, public;
revoke execute on function public.search_sermon_chunks(text, integer) from anon, public;
grant execute on function public.match_sermon_chunks(extensions.vector, integer) to authenticated;
grant execute on function public.search_sermon_chunks(text, integer) to authenticated;
