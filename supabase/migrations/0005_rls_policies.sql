-- Enable RLS on all application tables.
alter table projects        enable row level security;
alter table subtopics       enable row level security;
alter table sources         enable row level security;
alter table source_subtopics enable row level security;
alter table source_chunks   enable row level security;
alter table chat_messages   enable row level security;
alter table reports         enable row level security;
alter table jobs            enable row level security;
alter table worker_activity enable row level security;
alter table project_members enable row level security;

-- can_access_project: owner OR member. SECURITY DEFINER so it can read projects/members
-- without exposing them through RLS (the function itself is the gatekeeper).
create or replace function can_access_project(p_project_id uuid)
returns boolean
language sql
security definer
stable
as $$
  select exists (
    select 1 from projects       where id = p_project_id and owner_id = auth.uid()
    union all
    select 1 from project_members where project_id = p_project_id and user_id = auth.uid()
  );
$$;

-- can_write_project: owner OR collaborator (not viewer).
create or replace function can_write_project(p_project_id uuid)
returns boolean
language sql
security definer
stable
as $$
  select exists (
    select 1 from projects where id = p_project_id and owner_id = auth.uid()
    union all
    select 1 from project_members
      where project_id = p_project_id and user_id = auth.uid() and role = 'collaborator'
  );
$$;

-- ── projects ──────────────────────────────────────────────────────────────────
create policy "projects_select" on projects
  for select using (can_access_project(id));

create policy "projects_insert" on projects
  for insert with check (owner_id = auth.uid());

create policy "projects_update" on projects
  for update using (can_write_project(id));

create policy "projects_delete" on projects
  for delete using (owner_id = auth.uid());

-- ── subtopics ─────────────────────────────────────────────────────────────────
create policy "subtopics_select" on subtopics
  for select using (can_access_project(project_id));

create policy "subtopics_insert" on subtopics
  for insert with check (can_write_project(project_id));

create policy "subtopics_update" on subtopics
  for update using (can_write_project(project_id));

create policy "subtopics_delete" on subtopics
  for delete using (can_write_project(project_id));

-- ── sources ───────────────────────────────────────────────────────────────────
create policy "sources_select" on sources
  for select using (can_access_project(project_id));

create policy "sources_insert" on sources
  for insert with check (can_write_project(project_id));

create policy "sources_update" on sources
  for update using (can_write_project(project_id));

create policy "sources_delete" on sources
  for delete using (can_write_project(project_id));

-- ── source_subtopics ──────────────────────────────────────────────────────────
create policy "source_subtopics_select" on source_subtopics
  for select using (can_access_project(project_id));

create policy "source_subtopics_insert" on source_subtopics
  for insert with check (can_write_project(project_id));

create policy "source_subtopics_delete" on source_subtopics
  for delete using (can_write_project(project_id));

-- ── source_chunks ─────────────────────────────────────────────────────────────
create policy "source_chunks_select" on source_chunks
  for select using (can_access_project(project_id));

create policy "source_chunks_insert" on source_chunks
  for insert with check (can_write_project(project_id));

create policy "source_chunks_delete" on source_chunks
  for delete using (can_write_project(project_id));

-- ── chat_messages ─────────────────────────────────────────────────────────────
create policy "chat_messages_select" on chat_messages
  for select using (can_access_project(project_id));

create policy "chat_messages_insert" on chat_messages
  for insert with check (can_write_project(project_id));

-- ── reports ───────────────────────────────────────────────────────────────────
create policy "reports_select" on reports
  for select using (can_access_project(project_id));

create policy "reports_insert" on reports
  for insert with check (can_write_project(project_id));

create policy "reports_delete" on reports
  for delete using (can_write_project(project_id));

-- ── jobs ──────────────────────────────────────────────────────────────────────
-- Browser/Next.js can read job status; only owner/collaborator can enqueue.
-- The worker uses a direct DB connection that bypasses RLS by design.
create policy "jobs_select" on jobs
  for select using (can_access_project(project_id));

create policy "jobs_insert" on jobs
  for insert with check (can_write_project(project_id));

-- ── worker_activity ───────────────────────────────────────────────────────────
create policy "worker_activity_select" on worker_activity
  for select using (can_access_project(project_id));

-- ── project_members ───────────────────────────────────────────────────────────
create policy "project_members_select" on project_members
  for select using (can_access_project(project_id));

create policy "project_members_insert" on project_members
  for insert with check (
    exists (select 1 from projects where id = project_id and owner_id = auth.uid())
  );

create policy "project_members_delete" on project_members
  for delete using (
    exists (select 1 from projects where id = project_id and owner_id = auth.uid())
  );
