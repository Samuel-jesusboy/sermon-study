-- Sermon documentation format: fields for the curated 11-section document.
alter table public.sermons
  add column if not exists sermon_date date,
  add column if not exists series text not null default '',
  add column if not exists main_text text not null default '',
  add column if not exists central_message text not null default '',
  add column if not exists main_points jsonb not null default '[]',
  add column if not exists explanations jsonb not null default '[]',
  add column if not exists key_takeaways jsonb not null default '[]',
  add column if not exists curation_version integer not null default 1;

create index if not exists sermons_user_series_idx on public.sermons (user_id, series);
create index if not exists sermons_user_date_idx on public.sermons (user_id, sermon_date desc);
