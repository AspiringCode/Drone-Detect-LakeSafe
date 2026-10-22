-- Each lease carries an opaque generation token.  Only its current holder can
-- complete or fail it after a stale lease has been reclaimed.

alter table public.risk_refresh_jobs add column claim_token uuid;
alter table public.risk_source_refresh_state add column claim_token uuid;

-- PostgreSQL cannot replace a TABLE return type when adding claim_token.
-- Recreate both claim functions and restore their server-only grants below.
drop function public.claim_queued_risk_refreshes(integer);
drop function public.claim_due_risk_source_refreshes(integer);

create or replace function public.claim_queued_risk_refreshes(p_limit integer default 25)
returns table(lake_id text, claim_token uuid) language plpgsql security definer set search_path = '' as $$
begin
  return query
  with claimed as (
    select job.lake_id from public.risk_refresh_jobs as job
    where job.next_attempt_at <= now() and (job.status in ('queued', 'failed') or
      (job.status = 'processing' and job.claimed_at < now() - interval '10 minutes'))
    order by job.next_attempt_at, job.requested_at for update skip locked limit greatest(1, least(p_limit, 100))
  )
  update public.risk_refresh_jobs as job set status = 'processing', claimed_at = now(), claim_token = gen_random_uuid()
  from claimed where job.lake_id = claimed.lake_id
  returning job.lake_id, job.claim_token;
end;
$$;

create or replace function public.claim_due_risk_source_refreshes(p_limit integer default 25)
returns table(lake_id text, claim_token uuid) language plpgsql security definer set search_path = '' as $$
begin
  return query
  with claimed as (
    select state.lake_data_source_id, source.lake_id from public.risk_source_refresh_state as state
    join public.lake_data_sources as source using (lake_data_source_id)
    where state.next_refresh_at <= now() and (state.claimed_at is null or state.claimed_at < now() - interval '10 minutes')
    order by state.next_refresh_at for update of state skip locked limit greatest(1, least(p_limit, 100))
  )
  update public.risk_source_refresh_state as state set claimed_at = now(), claim_token = gen_random_uuid()
  from claimed where state.lake_data_source_id = claimed.lake_data_source_id
  returning claimed.lake_id, state.claim_token;
end;
$$;

create or replace function public.complete_risk_refresh(p_lake_id text, p_claim_token uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  update public.risk_refresh_jobs set status = 'complete', completed_at = now(), claimed_at = null, claim_token = null, failure_reason = null
  where lake_id = p_lake_id and status = 'processing' and claim_token = p_claim_token;
  if found then return true; end if;
  update public.risk_source_refresh_state as state set claimed_at = null, claim_token = null,
    next_refresh_at = now() + interval '24 hours', last_failure_reason = null
  from public.lake_data_sources as source
  where state.lake_data_source_id = source.lake_data_source_id and source.lake_id = p_lake_id and state.claim_token = p_claim_token;
  return found;
end;
$$;

create or replace function public.fail_risk_refresh(p_lake_id text, p_claim_token uuid, p_reason text)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  update public.risk_refresh_jobs set status = 'failed', claimed_at = null, claim_token = null,
    next_attempt_at = now() + interval '15 minutes', failure_reason = left(coalesce(nullif(p_reason, ''), 'unknown failure'), 500)
  where lake_id = p_lake_id and status = 'processing' and claim_token = p_claim_token;
  if found then return true; end if;
  update public.risk_source_refresh_state as state set claimed_at = null, claim_token = null,
    next_refresh_at = now() + interval '15 minutes', last_failure_reason = left(coalesce(nullif(p_reason, ''), 'unknown failure'), 500)
  from public.lake_data_sources as source
  where state.lake_data_source_id = source.lake_data_source_id and source.lake_id = p_lake_id and state.claim_token = p_claim_token;
  return found;
end;
$$;

revoke all on function public.claim_queued_risk_refreshes(integer), public.claim_due_risk_source_refreshes(integer), public.complete_risk_refresh(text, uuid), public.fail_risk_refresh(text, uuid, text) from public, anon, authenticated;
grant execute on function public.claim_queued_risk_refreshes(integer), public.claim_due_risk_source_refreshes(integer), public.complete_risk_refresh(text, uuid), public.fail_risk_refresh(text, uuid, text) to service_role;
