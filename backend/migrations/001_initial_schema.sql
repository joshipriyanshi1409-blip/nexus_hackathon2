-- Migration 001: Initial schema for ECHO Brand Governance Platform
create table if not exists profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  username text unique not null,
  name text not null,
  role int not null check (role between 0 and 3),      -- 0 CEO, 1 Head, 2 Supervisor, 3 Employee
  powers text[] not null default '{}',
  created_by uuid references profiles(id) on delete set null,
  expires_at timestamptz,
  created_at timestamptz default now()
);

create table if not exists brand_rules (
  id int primary key default 1 check (id = 1),
  rules jsonb not null,
  updated_at timestamptz default now()
);

create table if not exists brand_sources (            -- knowledge base: guidelines, facts, terminology, assets
  id bigserial primary key,
  kind text not null check (kind in ('guidelines','facts','terminology','asset')),
  title text not null,
  content text default '',
  storage_path text,
  uploaded_by uuid references profiles(id),
  created_at timestamptz default now()
);

create table if not exists reviews (                  -- every AI review run (reproducible: model + hash)
  id bigserial primary key,
  user_id uuid references profiles(id),
  text_hash text not null,
  findings jsonb not null,
  model text,
  used_ai boolean default false,
  created_at timestamptz default now()
);

create table if not exists posts (
  id bigserial primary key,
  author_id uuid references profiles(id),
  text text not null,
  issues int default 0,
  findings jsonb default '[]',
  review_id bigint references reviews(id),
  status text not null default 'Waiting' check (status in ('Waiting','Recommended','Approved','Sent back')),
  note text default '',
  created_at timestamptz default now()
);

create table if not exists post_events (               -- revision / comment history
  id bigserial primary key,
  post_id bigint references posts(id) on delete cascade,
  actor_id uuid references profiles(id),
  action text not null,
  note text default '',
  created_at timestamptz default now()
);

create table if not exists folders (
  id bigserial primary key,
  name text not null,
  created_by uuid references profiles(id),
  created_at timestamptz default now()
);

create table if not exists folder_access (
  folder_id bigint references folders(id) on delete cascade,
  user_id uuid references profiles(id) on delete cascade,
  level text not null,
  primary key (folder_id, user_id)
);

create table if not exists files (
  id bigserial primary key,
  folder_id bigint references folders(id) on delete cascade,
  name text not null,
  version int not null default 1,
  storage_path text not null,
  size bigint,
  uploaded_by uuid references profiles(id),
  created_at timestamptz default now()
);

create table if not exists feedback (
  id bigserial primary key,
  source text not null,
  text text not null,
  rating int check (rating between 1 and 5),
  sentiment text,
  topic text,
  happened_at text,
  created_at timestamptz default now()
);

create table if not exists audit_log (
  id bigserial primary key,
  actor_id uuid,
  action text not null,
  detail text,
  created_at timestamptz default now()
);

-- Enable RLS on all tables
do $$ declare t text; begin
  for t in select unnest(array['profiles','brand_rules','brand_sources','reviews','posts','post_events','folders','folder_access','files','feedback','audit_log']) loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;
