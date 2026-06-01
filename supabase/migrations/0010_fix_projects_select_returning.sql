-- Bug #1 fix — project creation failed with 42501 "new row violates row-level
-- security policy for table projects".
--
-- Root cause: `createProject` inserts with `.select()` (INSERT ... RETURNING).
-- RETURNING requires the SELECT policy to pass on the new row. The original
-- projects_select policy was `using (can_access_project(id))`, and
-- can_access_project() determines ownership by RE-QUERYING the projects table
-- (`select 1 from projects where id = p_project_id and owner_id = auth.uid()`).
-- During INSERT ... RETURNING the just-inserted row is not visible to that
-- lookup's snapshot, so the function returns false, the row fails the SELECT
-- policy, and the whole statement is rejected. (Plain INSERT without RETURNING
-- succeeded, since only the INSERT WITH CHECK was evaluated.)
--
-- Fix: check ownership DIRECTLY on the row (`owner_id = auth.uid()`), which is
-- valid during RETURNING, and keep the SECURITY DEFINER helper only for the
-- shared-member case (it must stay a function to avoid projects<->project_members
-- RLS recursion). Owners and members keep exactly the same visibility as before;
-- non-members still cannot read. This applies to all users, not just the owner.
--
-- Child tables (subtopics, sources, ...) are unaffected: their policies call
-- can_access_project(project_id) against the already-committed PARENT project.

drop policy if exists "projects_select" on projects;

create policy "projects_select" on projects
  for select using (
    owner_id = auth.uid()
    or can_access_project(id)
  );
