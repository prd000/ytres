create type job_status as enum ('queued', 'running', 'done', 'failed', 'cancelled');

-- jobs — the durable work queue (FOR UPDATE SKIP LOCKED claim model)
create table jobs (
  id           uuid       primary key default gen_random_uuid(),
  project_id   uuid       not null references projects(id) on delete cascade,
  type         text       not null,
  status       job_status not null default 'queued',
  payload      jsonb      not null default '{}',
  attempts     integer    not null default 0,
  max_attempts integer    not null default 3,
  last_error   text,
  heartbeat_at timestamptz,
  claimed_by   text,
  claimed_at   timestamptz,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- Partial indexes: claim scan only touches queued rows; stale-job scan only touches running rows.
create index jobs_queued_idx  on jobs (created_at) where status = 'queued';
create index jobs_running_idx on jobs (heartbeat_at) where status = 'running';

-- worker_activity — one row per subtopic; upserted by the worker at each activity step
create table worker_activity (
  subtopic_id        uuid            primary key references subtopics(id) on delete cascade,
  project_id         uuid            not null references projects(id) on delete cascade,
  latest_activity    text            not null default '',
  sources_stored     integer         not null default 0,
  status             subtopic_status not null default 'queued',
  why_nothing_report text,
  updated_at         timestamptz     not null default now()
);

-- Add to Realtime publication (Phase 7)
alter publication supabase_realtime add table jobs, worker_activity;
