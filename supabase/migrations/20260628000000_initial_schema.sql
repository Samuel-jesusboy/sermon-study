-- Sermon Study v1 schema (June 2026). Later migrations add accounts, jobs and search.

-- Full sermons table
create table if not exists sermons (
  id uuid default gen_random_uuid() primary key,
  video_id text,
  youtube_url text,
  church_name text default '',
  preacher text default '',
  title text,
  summary text,
  main_theme text,
  introduction jsonb default '{}',
  full_notes jsonb default '[]',
  theological_depths jsonb default '[]',
  all_bible_verses jsonb default '[]',
  notable_quotes jsonb default '[]',
  conclusion jsonb default '{}',
  practical_applications jsonb default '[]',
  prayer_points jsonb default '[]',
  study_questions jsonb default '[]',
  weekly_challenge text default '',
  related_topics jsonb default '[]',
  sermon_character text default '',
  sermon_start_seconds integer default 0,
  sermon_start_info jsonb default '{}',
  timed_chunks jsonb default '[]',
  full_transcript text,
  sermon_transcript text,
  model_used text default 'claude',
  created_at timestamptz default now()
);

-- Churches table
create table if not exists churches (
  id uuid default gen_random_uuid() primary key,
  name text not null,
  youtube_channel_url text not null,
  description text default '',
  playlist_url text default '',
  created_at timestamptz default now()
);

-- Study guides table
create table if not exists study_guides (
  id uuid default gen_random_uuid() primary key,
  weeks integer default 4,
  theme text default '',
  content text,
  model_used text default 'claude',
  sermons_count integer default 0,
  created_at timestamptz default now()
);

-- Enable Row Level Security
alter table sermons enable row level security;
alter table churches enable row level security;
alter table study_guides enable row level security;

create policy "Allow all" on sermons for all using (true) with check (true);
create policy "Allow all" on churches for all using (true) with check (true);
create policy "Allow all" on study_guides for all using (true) with check (true);
