-- AI usage and cost tracking: one row per AI call (chat, embedding or transcription).
create table if not exists public.ai_usage (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  task text not null,                 -- notes, start, ask, verse, guide, embed, transcribe
  provider text not null,             -- openai, claude, groq
  model text not null,
  input_tokens integer not null default 0,
  cached_tokens integer not null default 0,
  output_tokens integer not null default 0,
  audio_seconds numeric not null default 0,
  cost_usd numeric(12, 6),            -- null when the model has no known price
  sermon_id uuid references public.sermons (id) on delete set null,
  job_id uuid references public.jobs (id) on delete set null
);
create index if not exists ai_usage_user_created_idx on public.ai_usage (user_id, created_at desc);
create index if not exists ai_usage_sermon_idx on public.ai_usage (sermon_id);
create index if not exists ai_usage_job_idx on public.ai_usage (job_id);

alter table public.ai_usage enable row level security;
create policy "ai_usage_select_own" on public.ai_usage
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "ai_usage_insert_own" on public.ai_usage
  for insert to authenticated with check ((select auth.uid()) = user_id);

grant select, insert on public.ai_usage to authenticated;
grant usage, select on all sequences in schema public to authenticated;
grant all on public.ai_usage to service_role;

alter table public.jobs add column if not exists cost_usd numeric(12, 6);
alter table public.sermons
  add column if not exists cost_usd numeric(12, 6) not null default 0,
  add column if not exists models_used jsonb not null default '{}';
