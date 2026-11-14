-- Migration 003: consistency + safety fixes.
-- Safe to re-run: every statement is idempotent.

-- 1. Departments live in a real column (profiles.department), not as a 'dept:X' tag hidden inside powers.
alter table profiles add column if not exists department text default 'General';

update profiles p
   set department = coalesce(
         (select substr(x, 6) from unnest(p.powers) as x where x like 'dept:%' limit 1),
         nullif(p.department, ''),
         'General')
 where exists (select 1 from unnest(p.powers) as x where x like 'dept:%');

update profiles
   set powers = array(select x from unnest(powers) as x where x not like 'dept:%')
 where exists (select 1 from unnest(powers) as x where x like 'dept:%');

-- 2. Columns the application relies on.
alter table folders       add column if not exists is_confidential boolean default true;
alter table folder_access add column if not exists expires_at timestamptz;

-- 3. Removing a person must not be blocked by rows they created or uploaded.
alter table folders drop constraint if exists folders_created_by_fkey;
alter table folders add constraint folders_created_by_fkey
  foreign key (created_by) references profiles(id) on delete set null;

alter table files drop constraint if exists files_uploaded_by_fkey;
alter table files add constraint files_uploaded_by_fkey
  foreign key (uploaded_by) references profiles(id) on delete set null;

alter table brand_sources drop constraint if exists brand_sources_uploaded_by_fkey;
alter table brand_sources add constraint brand_sources_uploaded_by_fkey
  foreign key (uploaded_by) references profiles(id) on delete set null;

alter table post_events drop constraint if exists post_events_actor_id_fkey;
alter table post_events add constraint post_events_actor_id_fkey
  foreign key (actor_id) references profiles(id) on delete set null;

-- 4. Tables from migration 002 that nothing ever used (the app stores these in posts / reviews / post_events).
drop table if exists post_comments;
drop table if exists finding_actions;
drop table if exists brand_source_chunks;
drop table if exists departments;

-- 5. Indexes for the queries the app actually runs.
create index if not exists idx_posts_author     on posts(author_id);
create index if not exists idx_posts_review     on posts(review_id);
create index if not exists idx_post_events_post on post_events(post_id);
create index if not exists idx_files_folder_name on files(folder_id, name);
create index if not exists idx_audit_actor      on audit_log(actor_id);
create index if not exists idx_feedback_created on feedback(created_at);

-- 6. The migration bookkeeping table is locked down like every other table (no browser access).
alter table if exists _migrations enable row level security;
