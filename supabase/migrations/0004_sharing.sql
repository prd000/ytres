-- Groundwork for Phase 11 sharing; no invite UX built yet.
create type project_role as enum ('viewer', 'collaborator');

create table project_members (
  project_id uuid         not null references projects(id) on delete cascade,
  user_id    uuid         not null references auth.users(id) on delete cascade,
  role       project_role not null default 'viewer',
  created_at timestamptz  not null default now(),
  primary key (project_id, user_id)
);
