-- Durable refresh work is claimed server-side.  A claimant never holds a
-- browser-provided authority token, and SKIP LOCKED permits multiple backend
-- instances without executing the same lake concurrently.

create table public.risk_refresh_jobs (
  lake_id text primary key references public.lakes(lake_id) on delete restrict,
  reason text not null check (reason in ('initial', 'manual', 'source_due')),
  status text not null default 'queued' check (status in ('queued', 'processing', 'failed', 'complete')),
  requested_at timestamptz not null default now(),
  claimed_at timestamptz,
  completed_at timestamptz,
  failure_reason text
);

create table public.risk_source_refresh_state (
  lake_data_source_id uuid primary key references public.lake_data_sources(lake_data_source_id) on delete restrict,
  next_refresh_at timestamptz not null default now(),
  last_fresh_through timestamptz,
  last_failure_reason text,
  claimed_at timestamptz
);

alter table public.risk_refresh_jobs enable row level security;
alter table public.risk_refresh_jobs force row level security;
alter table public.risk_source_refresh_state enable row level security;
alter table public.risk_source_refresh_state force row level security;
revoke all on public.risk_refresh_jobs, public.risk_source_refresh_state from public, anon, authenticated;

create function public.enqueue_risk_refresh(p_lake_id text, p_reason text default 'manual')
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not exists (select 1 from public.lakes where lake_id = p_lake_id) then
    raise exception 'lake not found' using errcode = 'P0002';
  end if;
  insert into public.risk_refresh_jobs (lake_id, reason, status, requested_at, claimed_at, completed_at, failure_reason)
  values (p_lake_id, p_reason, 'queued', now(), null, null, null)
  on conflict (lake_id) do update set reason = excluded.reason, status = 'queued',
    requested_at = excluded.requested_at, claimed_at = null, failure_reason = null;
end;
$$;

create function public.claim_queued_risk_refreshes(p_limit integer default 25)
returns table(lake_id text) language plpgsql security definer set search_path = '' as $$
begin
  return query
  with claimed as (
    select job.lake_id from public.risk_refresh_jobs as job
    where job.status in ('queued', 'failed')
    order by job.requested_at
    for update skip locked limit greatest(1, least(p_limit, 100))
  )
  update public.risk_refresh_jobs as job set status = 'processing', claimed_at = now()
  from claimed where job.lake_id = claimed.lake_id
  returning job.lake_id;
end;
$$;

create function public.claim_due_risk_source_refreshes(p_limit integer default 25)
returns table(lake_id text) language plpgsql security definer set search_path = '' as $$
begin
  return query
  with claimed as (
    select state.lake_data_source_id, source.lake_id from public.risk_source_refresh_state as state
    join public.lake_data_sources as source using (lake_data_source_id)
    where state.next_refresh_at <= now() and state.claimed_at is null
    order by state.next_refresh_at
    for update of state skip locked limit greatest(1, least(p_limit, 100))
  )
  update public.risk_source_refresh_state as state set claimed_at = now()
  from claimed where state.lake_data_source_id = claimed.lake_data_source_id
  returning claimed.lake_id;
end;
$$;

create function public.complete_risk_refresh(p_lake_id text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  update public.risk_refresh_jobs set status = 'complete', completed_at = now(), claimed_at = null,
    failure_reason = null where lake_id = p_lake_id;
  -- The connector cadence is represented by the source's reviewed config;
  -- until a per-connector cadence is installed, this conservative 24h default
  -- prevents tight retry loops while preserving immutable snapshots/plans.
  update public.risk_source_refresh_state as state set claimed_at = null,
    next_refresh_at = now() + interval '24 hours', last_failure_reason = null
  from public.lake_data_sources as source
  where state.lake_data_source_id = source.lake_data_source_id and source.lake_id = p_lake_id;
end;
$$;

create function public.fail_risk_refresh(p_lake_id text, p_reason text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  update public.risk_refresh_jobs set status = 'failed', claimed_at = null,
    failure_reason = left(coalesce(nullif(p_reason, ''), 'unknown failure'), 500)
  where lake_id = p_lake_id;
  update public.risk_source_refresh_state as state set claimed_at = null,
    next_refresh_at = now() + interval '15 minutes',
    last_failure_reason = left(coalesce(nullif(p_reason, ''), 'unknown failure'), 500)
  from public.lake_data_sources as source
  where state.lake_data_source_id = source.lake_data_source_id and source.lake_id = p_lake_id;
end;
$$;

revoke all on function public.enqueue_risk_refresh(text, text),
  public.claim_queued_risk_refreshes(integer), public.claim_due_risk_source_refreshes(integer),
  public.complete_risk_refresh(text), public.fail_risk_refresh(text, text) from public, anon, authenticated;
grant execute on function public.enqueue_risk_refresh(text, text),
  public.claim_queued_risk_refreshes(integer), public.claim_due_risk_source_refreshes(integer),
  public.complete_risk_refresh(text), public.fail_risk_refresh(text, text) to service_role;
