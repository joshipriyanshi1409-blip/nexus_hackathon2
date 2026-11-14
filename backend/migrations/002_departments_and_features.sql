-- Migration 002: Departments, confidentiality flags, source chunks & comments
create table if not exists departments (
  id bigserial primary key,
  name text unique not null,
  description text default '',
  created_at timestamptz default now()
);

-- Add department_id to profiles if not exists
do $$ begin
  alter table profiles add column if not exists department text default 'General';
exception
  when others then null;
end $$;

-- Add confidentiality flag to folders
do $$ begin
  alter table folders add column if not exists is_confidential boolean default true;
exception
  when others then null;
end $$;

-- Add expires_at to folder_access
do $$ begin
  alter table folder_access add column if not exists expires_at timestamptz;
exception
  when others then null;
end $$;

-- Knowledge base chunking & embeddings
create table if not exists brand_source_chunks (
  id bigserial primary key,
  source_id bigint references brand_sources(id) on delete cascade,
  chunk_index int not null,
  content text not null,
  created_at timestamptz default now()
);

-- Per-finding actions (accept, reject, edit)
create table if not exists finding_actions (
  id bigserial primary key,
  review_id bigint references reviews(id) on delete cascade,
  finding_id text not null,
  action text not null check (action in ('accepted', 'rejected', 'edited')),
  edited_text text default '',
  user_id uuid references profiles(id),
  created_at timestamptz default now()
);

-- Inline quoted comments for posts
create table if not exists post_comments (
  id bigserial primary key,
  post_id bigint references posts(id) on delete cascade,
  author_id uuid references profiles(id),
  quote text not null,
  comment text not null,
  created_at timestamptz default now()
);

-- Enable RLS on new tables
do $$ declare t text; begin
  for t in select unnest(array['departments','brand_source_chunks','finding_actions','post_comments']) loop
    begin
      execute format('alter table %I enable row level security', t);
    exception
      when others then null;
    end;
  end loop;
end $$;
