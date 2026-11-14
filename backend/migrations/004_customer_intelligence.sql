-- Customer intelligence, deduplication, automatic connectors and approved facts.
-- Idempotent: safe to apply more than once.
alter table feedback add column if not exists content_hash text;
alter table feedback add column if not exists external_id text;
alter table feedback add column if not exists pii_redactions int not null default 0;
-- Backfill old rows with source-scoped hashes; keep one copy if historical duplicates exist.
with ranked as (
  select id, row_number() over (partition by lower(trim(source)), lower(regexp_replace(trim(text), '\s+', ' ', 'g')) order by id) as rn,
         md5(lower(trim(source)) || '|' || lower(regexp_replace(trim(text), '\s+', ' ', 'g'))) as h
  from feedback
)
update feedback f set content_hash = case when ranked.rn = 1 then ranked.h else null end
from ranked where f.id = ranked.id and f.content_hash is null;

create unique index if not exists idx_feedback_content_hash_unique
  on feedback(content_hash) where content_hash is not null;
create unique index if not exists idx_feedback_source_external_unique
  on feedback(source, external_id) where external_id is not null;
create index if not exists idx_feedback_happened_at on feedback(happened_at);

create table if not exists approved_facts (
  id bigserial primary key,
  name text not null,
  value text not null,
  source_title text not null,
  source_url text default '',
  created_by uuid references profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  unique(name)
);
alter table approved_facts enable row level security;
create index if not exists idx_approved_facts_name on approved_facts(name);
