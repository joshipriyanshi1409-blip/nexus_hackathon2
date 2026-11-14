-- Backward-compatible demo metadata fields used by the sample-data tooling.
-- These columns are metadata only: API access is governed by each account's
-- normal role/powers, not by an is_demo restriction. Approved facts are keyed
-- by name plus metadata flag so legacy and live demo facts can coexist.
alter table profiles
  add column if not exists is_demo boolean not null default false;

alter table approved_facts
  add column if not exists is_demo boolean not null default false;

alter table approved_facts
  drop constraint if exists approved_facts_name_key;

create unique index if not exists idx_approved_facts_name_scope_unique
  on approved_facts(name, is_demo);

create index if not exists idx_profiles_is_demo
  on profiles(is_demo);
create index if not exists idx_approved_facts_is_demo
  on approved_facts(is_demo);
