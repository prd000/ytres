-- Phase 8: Coordinator review barrier
-- 1a. wave column on subtopics (initial plan = 0, gap-fill = 1)
alter table subtopics add column wave smallint not null default 0;

-- 1b. Set-based barrier RPC — sweep calls this every COORDINATOR_SWEEP_INTERVAL.
-- Advisory lock serializes concurrent sweeps; NOT EXISTS guards are idempotent.
create or replace function enqueue_ready_coordinator_reviews()
returns integer language plpgsql security definer as $$
declare v_count integer;
begin
  perform pg_advisory_xact_lock(81273401);  -- serialize concurrent sweeps
  insert into jobs (project_id, type, payload)
  select p.id, 'coordinator_review',
         jsonb_build_object('project_id', p.id::text, 'wave', rev.next_wave)
  from projects p
  cross join lateral (
    select (select count(*) from jobs j
            where j.project_id = p.id and j.type = 'coordinator_review') + 1 as next_wave
  ) rev
  where p.status = 'researching'
    and rev.next_wave <= 2                                    -- two-wave cap
    and exists (select 1 from jobs j                          -- research actually ran
                where j.project_id = p.id and j.type = 'research_subtopic')
    and not exists (select 1 from jobs j                      -- nothing still in flight
                    where j.project_id = p.id and j.type = 'research_subtopic'
                      and j.status in ('queued','running'))
    and not exists (select 1 from jobs j                      -- idempotent per wave
                    where j.project_id = p.id and j.type = 'coordinator_review'
                      and (j.payload->>'wave')::int = rev.next_wave);
  get diagnostics v_count = row_count;
  return v_count;
end; $$;

-- Hard backstop unique index (advisory lock is the primary guard; this is defense-in-depth)
create unique index jobs_review_wave_uniq
  on jobs (project_id, ((payload->>'wave'))) where type = 'coordinator_review';

-- 1c. Worker-owned status transition — guards so it no-ops unless currently researching.
create or replace function complete_research(p_project_id uuid)
returns void language plpgsql security definer as $$
begin
  update projects set status = 'complete', updated_at = now()
  where id = p_project_id and status = 'researching';
end; $$;
