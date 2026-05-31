-- Enums — mirror types.ts exactly so the TS domain types swap cleanly.
create type project_status  as enum ('draft', 'planning', 'researching', 'complete', 'cancelled');
create type source_tier     as enum ('academic', 'government', 'news', 'industry');
create type subtopic_status as enum ('queued', 'running', 'complete', 'failed', 'cancelled');
create type chat_role       as enum ('user', 'assistant');

-- projects
create table projects (
  id                   uuid        primary key default gen_random_uuid(),
  owner_id             uuid        not null references auth.users(id) on delete cascade,
  research_question    text        not null,
  status               project_status not null default 'draft',
  source_tier_settings jsonb       not null default '{}',
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);

-- subtopics
create table subtopics (
  id                      uuid            primary key default gen_random_uuid(),
  project_id              uuid            not null references projects(id) on delete cascade,
  title                   text            not null,
  information_objective   text            not null,
  source_tier_preferences source_tier[]   not null default '{}',
  status                  subtopic_status not null default 'queued',
  sort_order              integer         not null default 0,
  created_at              timestamptz     not null default now(),
  updated_at              timestamptz     not null default now()
);

-- sources — unique (project_id, url) enforces URL-based dedup
create table sources (
  id                  uuid        primary key default gen_random_uuid(),
  project_id          uuid        not null references projects(id) on delete cascade,
  url                 text        not null,
  title               text        not null,
  full_text           text        not null default '',
  tier                source_tier not null,
  key_takeaway        text        not null default '',
  score_relevance     numeric(3,1) not null default 0,
  score_credibility   numeric(3,1) not null default 0,
  score_uniqueness    numeric(3,1) not null default 0,
  score_actionability numeric(3,1) not null default 0,
  stored_at           timestamptz not null default now(),
  created_at          timestamptz not null default now(),
  unique (project_id, url)
);

-- source_subtopics — many-to-many; source appears once per project even if linked to multiple subtopics
create table source_subtopics (
  source_id   uuid not null references sources(id)   on delete cascade,
  subtopic_id uuid not null references subtopics(id) on delete cascade,
  project_id  uuid not null references projects(id)  on delete cascade,
  primary key (source_id, subtopic_id)
);

-- source_chunks — fixed-size ~500-token chunks; ivfflat/hnsw index deferred to Phase 4
create table source_chunks (
  id          uuid    primary key default gen_random_uuid(),
  source_id   uuid    not null references sources(id)  on delete cascade,
  project_id  uuid    not null references projects(id) on delete cascade,
  chunk_index integer not null,
  content     text    not null,
  embedding   vector(1536),
  token_count integer,
  created_at  timestamptz not null default now()
);

-- chat_messages
create table chat_messages (
  id         uuid      primary key default gen_random_uuid(),
  project_id uuid      not null references projects(id) on delete cascade,
  role       chat_role not null,
  content    text      not null,
  citations  jsonb     not null default '[]',
  created_at timestamptz not null default now()
);

-- reports
create table reports (
  id           uuid   primary key default gen_random_uuid(),
  project_id   uuid   not null references projects(id) on delete cascade,
  markdown     text   not null,
  source_refs  uuid[] not null default '{}',
  generated_at timestamptz not null default now(),
  created_at   timestamptz not null default now()
);

-- Realtime publication — tables subscribed to in Phase 7
alter publication supabase_realtime add table projects, subtopics, sources, source_subtopics;
