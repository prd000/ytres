-- Queue RPCs — all SECURITY DEFINER so the caller (Next.js server or worker) does not need
-- elevated DB privileges. The worker also connects directly and bypasses RLS, but having these
-- as RPCs keeps the claim logic canonical and testable.

-- claim_job: atomically claim the oldest queued job for this worker.
-- Uses FOR UPDATE SKIP LOCKED so concurrent workers never double-claim.
create or replace function claim_job(p_worker_id text)
returns setof jobs
language plpgsql
security definer
as $$
declare
  v_job jobs;
begin
  select * into v_job
  from jobs
  where status = 'queued'
  order by created_at
  limit 1
  for update skip locked;

  if not found then
    return;
  end if;

  update jobs set
    status      = 'running',
    attempts    = attempts + 1,
    claimed_by  = p_worker_id,
    claimed_at  = now(),
    heartbeat_at = now(),
    updated_at  = now()
  where id = v_job.id
  returning * into v_job;

  return next v_job;
end;
$$;

-- heartbeat_job: bump heartbeat_at; optionally checkpoint payload; return current status.
-- The worker reads the returned status: if 'cancelled', it stops the handler.
create or replace function heartbeat_job(p_id uuid, p_payload jsonb default null)
returns table(status job_status)
language plpgsql
security definer
as $$
begin
  update jobs set
    heartbeat_at = now(),
    payload      = coalesce(p_payload, payload),
    updated_at   = now()
  where id = p_id;

  return query select j.status from jobs j where j.id = p_id;
end;
$$;

-- reclaim_stale_jobs: any running job whose heartbeat is older than p_timeout_seconds goes back
-- to queued (if under max_attempts) or to failed.
create or replace function reclaim_stale_jobs(p_timeout_seconds integer)
returns void
language plpgsql
security definer
as $$
begin
  -- Jobs that still have retries left → requeue
  update jobs set
    status       = 'queued',
    claimed_by   = null,
    claimed_at   = null,
    heartbeat_at = null,
    updated_at   = now()
  where status = 'running'
    and heartbeat_at < now() - (p_timeout_seconds || ' seconds')::interval
    and attempts < max_attempts;

  -- Jobs that exhausted retries → fail
  update jobs set
    status     = 'failed',
    last_error = 'reclaimed after stale heartbeat',
    updated_at = now()
  where status = 'running'
    and heartbeat_at < now() - (p_timeout_seconds || ' seconds')::interval
    and attempts >= max_attempts;
end;
$$;

-- complete_job: mark a job done.
create or replace function complete_job(p_id uuid)
returns void
language plpgsql
security definer
as $$
begin
  update jobs set status = 'done', updated_at = now() where id = p_id;
end;
$$;

-- fail_job: record error; if under max_attempts reset to queued for retry, else mark failed.
create or replace function fail_job(p_id uuid, p_error text)
returns void
language plpgsql
security definer
as $$
declare
  v_attempts     integer;
  v_max_attempts integer;
begin
  select attempts, max_attempts into v_attempts, v_max_attempts
  from jobs where id = p_id;

  if v_attempts < v_max_attempts then
    update jobs set
      status       = 'queued',
      last_error   = p_error,
      claimed_by   = null,
      claimed_at   = null,
      heartbeat_at = null,
      updated_at   = now()
    where id = p_id;
  else
    update jobs set
      status     = 'failed',
      last_error = p_error,
      updated_at = now()
    where id = p_id;
  end if;
end;
$$;

-- cancel_project_jobs: cancel all queued or running jobs for a project (called on project cancel).
create or replace function cancel_project_jobs(p_project_id uuid)
returns void
language plpgsql
security definer
as $$
begin
  update jobs set
    status     = 'cancelled',
    updated_at = now()
  where project_id = p_project_id
    and status in ('queued', 'running');
end;
$$;
